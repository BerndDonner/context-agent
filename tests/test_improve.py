from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

import pytest

from context_agent.bundling import build_job_bundle
from context_agent.errors import ConfigurationError
from context_agent.improvement import improvement_diff, improvement_guard
from context_agent.job import load_job
from context_agent.prompts import render_initial_prompt
from context_agent.workflow import run_job
from test_workflow import FakeSession, configure_bad_word_rule


def improve_job(tmp_path: Path, job_factory, *, source: str = '\\starttext\nBAD 1{,}5 V\n\\stoptext\n') -> Path:
    root = job_factory(tmp_path, max_turns=15)
    (root / 'input/main.tex').write_text(source, encoding='utf-8')
    (root / 'job.yaml').write_text((root / 'job.yaml').read_text().replace(
        'mode: create', 'mode: improve\nsource:\n  path: input/main.tex'))
    (root / 'task.md').write_text('Korrigiere nur die Qualität, nicht Messwerte.', encoding='utf-8')
    return root


def test_missing_mode_rejected(tmp_path, job_factory):
    root = job_factory(tmp_path)
    yaml = root / 'job.yaml'
    yaml.write_text(yaml.read_text().replace('mode: create\n', ''))
    with pytest.raises(ConfigurationError, match='mode'):
        load_job(root)


def test_improve_requires_source_and_forbids_reproduction(tmp_path, job_factory):
    root = job_factory(tmp_path)
    yaml = root / 'job.yaml'
    yaml.write_text(yaml.read_text().replace('mode: create', 'mode: improve'))
    with pytest.raises(ConfigurationError, match='source.path'):
        load_job(root)
    (root / 'input/main.tex').write_text('\\starttext test \\stoptext')
    yaml.write_text(yaml.read_text() + '\nsource:\n  path: input/main.tex\nreview:\n  reproduction: true\n')
    with pytest.raises(ConfigurationError, match='review.reproduction'):
        load_job(root)


def test_improve_bundle_seeds_verbatim_source_and_manifest(tmp_path, job_factory):
    root = improve_job(tmp_path, job_factory)
    resolved = load_job(root)
    bundle = root / 'bundle.tar.gz'
    runtime = Path(__file__).resolve().parents[1] / 'src/context_agent/resources/runtime'
    build_job_bundle(resolved, bundle, runtime)
    with tarfile.open(bundle) as tar:
        assert tar.extractfile('job/result/main.tex').read() == (root/'input/main.tex').read_bytes()
        assert b'"mode": "improve"' in tar.extractfile('agent-manifest.json').read()
    prompt = render_initial_prompt(resolved, Path(__file__).resolve().parents[1] /
                                   'src/context_agent/resources/prompts')
    assert 'Baseline-Compile' in prompt and 'KEINE NEUERZEUGUNG' in prompt


def test_numeric_guard_preserves_decimal_values_and_repetitions():
    old = r'\\starttext 1{,}5 V, 1{,}5 V, 2026. \\stoptext'
    new = r'\\starttext \\dn{1.5}\\unit{Volt}, \\dn{1.5}\\unit{Volt}, 2026. \\stoptext'
    assert improvement_guard(old, new) == []
    assert improvement_guard(old, new.replace('1.5', '15', 1))
    assert '--- source/main.tex' in improvement_diff(old, new)


class ImproveSession(FakeSession):
    def run_initial(self, prompt):
        assert 'Baseline-Compile' in prompt
        shutil.copy2(self.job.source_path, self.remote / 'main.tex')
        self._write_pdf_and_log()
        return self._turn('baseline', 'compiled existing tex')

    def run_followup(self, prompt, previous_response_id):
        self.followups.append(prompt)
        if 'bad_word' in prompt:
            old = (self.remote / 'main.tex').read_text()
            (self.remote / 'main.tex').write_text(old.replace('BAD', 'GOOD'))
            self._write_pdf_and_log()
        return self._turn('repair', 'modified')


def test_improve_preserves_source_and_compiles_existing_baseline(tmp_path, job_factory):
    root = improve_job(tmp_path, job_factory, source='\\starttext\nOK 1{,}5 V\n\\stoptext\n')
    original = (root/'input/main.tex').read_bytes()
    report = run_job(root, session_factory=lambda job,*_: ImproveSession(job))
    assert report.status == 'success', report.errors
    assert report.mode == 'improve'
    assert (root/'input/main.tex').read_bytes() == original
    assert (root/'result/main.tex').read_bytes() == original
    assert (root/'result/.baseline/main.tex').read_bytes() == original
    assert (root/'result/.validated/main.tex').read_bytes() == original
    assert (root/'result/changes.diff').read_text().strip() == '(unchanged)'
    assert 'changes.diff' in report.artifacts


def test_improve_refines_with_preexisting_uncertainties(tmp_path, job_factory):
    root = improve_job(tmp_path, job_factory)
    configure_bad_word_rule(root)
    class Uncertain(ImproveSession):
        def review_pages(self, prompt, previous_response_id, pages):
            if 'UNABHÄNGIGE REQUIREMENTS VALIDATION' in prompt:
                return self._turn('audit','{"status":"uncertain","findings":[],"uncertainties":["Scan A13 unklar"]}')
            return super().review_pages(prompt, previous_response_id, pages)
    report = run_job(root, session_factory=lambda job,*_: Uncertain(job))
    assert report.status == 'needs_review'
    assert 'GOOD' in (root/'result/main.tex').read_text()
    assert 'BAD' in (root/'input/main.tex').read_text()
    assert report.quality_repairs == 1
    assert any(item['event'] == 'regression_gate_passed' for item in report.quality_journal)


def test_improve_numeric_regression_rolls_back(tmp_path, job_factory):
    root = improve_job(tmp_path, job_factory)
    configure_bad_word_rule(root)
    class NumericRegression(ImproveSession):
        def run_followup(self, prompt, previous_response_id):
            turn = super().run_followup(prompt, previous_response_id)
            (self.remote/'main.tex').write_text((self.remote/'main.tex').read_text().replace('1{,}5', '7{,}5'))
            self._write_pdf_and_log()
            return turn
    report = run_job(root, session_factory=lambda job,*_: NumericRegression(job))
    assert report.status == 'needs_review', report.errors
    assert '1{,}5' in (root/'result/main.tex').read_text()
    assert any(i['event']=='rollback' and 'numeric' in i['reason'] for i in report.quality_journal)


def test_initial_compile_must_not_change_source(tmp_path, job_factory):
    root = improve_job(tmp_path, job_factory)
    report = run_job(root, session_factory=lambda job,*_: FakeSession(job))
    assert report.status == 'failed'
    assert any('initial compile changed' in error for error in report.errors)


def test_numeric_quality_checker_ignores_lua_and_mp_but_finds_real_numbers(tmp_path, job_factory):
    from context_agent.quality_rules import load_rules, run_checkers, QualityContext
    root = job_factory(tmp_path)
    yaml = root / 'job.yaml'
    yaml.write_text(yaml.read_text().replace('quality: []', 'quality:\n  - semantic_numbers'))
    job = load_job(root)
    main = root / 'result/main.tex'
    main.write_text('\\starttext\n'
                    '\\startluacode\nlocal v = 1.25\n\\stopluacode\n'
                    '\\startMPcode\ndraw (1.5cm, 2.5cm)--(3cm,4cm);\n\\stopMPcode\n'
                    'Datenwert 1{,}5\n\\stoptext\n')
    findings, errors = run_checkers(load_rules(job), QualityContext(job, main, None, None))
    assert not errors
    assert len(findings) == 1
    assert findings[0].line == 8


def test_unit_checker_detects_kohm_millivolt_and_percent(tmp_path, job_factory):
    from context_agent.quality_rules import load_rules, run_checkers, QualityContext
    root = job_factory(tmp_path)
    yaml = root / 'job.yaml'
    yaml.write_text(yaml.read_text().replace('quality: []', 'quality:\n  - number_with_unit'))
    job = load_job(root)
    file = root / 'result/main.tex'
    file.write_text('\\starttext\n2{,}5 kΩ; 20 mV; 1{,}25\\%; '
                    '\\m{30^\\circ}; 20\\unit{Volt}\\stoptext\n')
    findings, errors = run_checkers(load_rules(job), QualityContext(job, file, None, None))
    assert not errors
    assert len(findings) >= 4


def test_inherited_source_scan_markers_stay_open_even_if_audit_passes(tmp_path, job_factory):
    from context_agent.scan_markers import inherited_scan_uncertainties
    tex = '\\define[1]\\ScanUnklar{[Scan unklar: #1]}\n\\starttext\\ScanUnklar{Vorzeichen} [Index unklar]\\stoptext\n'
    root = improve_job(tmp_path, job_factory, source=tex)
    found = inherited_scan_uncertainties(root/'input/main.tex')
    assert len(found) == 2
    report = run_job(root, session_factory=lambda job,*_: ImproveSession(job))
    assert report.status == 'needs_review'
    assert 'Vorzeichen' in (root/'result/uncertainties.md').read_text()


def test_verified_delta_regression_rolls_back_without_baseline_review(tmp_path, job_factory):
    root = improve_job(tmp_path, job_factory)
    configure_bad_word_rule(root)
    audits = []
    class Regressing(ImproveSession):
        def review_pages(self, prompt, previous_response_id, pages):
            if 'UNABHÄNGIGE REQUIREMENTS VALIDATION' in prompt:
                audits.append(prompt)
                # Only after GOOD has been written; previous source was never audited.
                assert 'BAD' in prompt and 'GOOD' in prompt
                return self._turn('review', '''{"status":"failed","findings":[],
                    "uncertainties":[],"regressions":[{"message":"meaning changed",
                    "original_excerpt":"BAD 1{,}5 V","updated_excerpt":"GOOD 1{,}5 V"}]}''')
            return super().review_pages(prompt, previous_response_id, pages)
    report = run_job(root, session_factory=lambda job,*_: Regressing(job))
    assert report.status == 'needs_review'
    assert len(audits) == 1  # no 4x baseline re-audit
    assert 'BAD' in (root/'result/main.tex').read_text()
    assert any('verified new requirements regression' in item.get('reason', '')
               for item in report.quality_journal)


def test_regression_verification_requires_same_changed_hunk():
    from context_agent.requirements import parse_result, verify_regressions
    base = 'alpha\nBAD\nother\n'
    updated = 'alpha\nGOOD\nother\n'
    valid = parse_result('''{"status":"failed","findings":[],"uncertainties":[],
       "regressions":[{"message":"changed","original_excerpt":"BAD","updated_excerpt":"GOOD"}]}''')
    findings, uncertainties = verify_regressions(valid,base,updated)
    assert len(findings) == 1 and not uncertainties
    ungrounded = parse_result('''{"status":"failed","findings":[],"uncertainties":[],
       "regressions":[{"message":"imaginary","original_excerpt":"other","updated_excerpt":"GOOD"}]}''')
    findings, uncertainties = verify_regressions(ungrounded,base,updated)
    assert not findings and len(uncertainties) == 1
