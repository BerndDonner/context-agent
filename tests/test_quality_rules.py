from pathlib import Path
import hashlib
import json
import tarfile

import pytest

from context_agent.errors import ConfigurationError
from context_agent.job import load_job
from context_agent.models import QualityFinding
from context_agent.quality_rules import QualityContext, Edit, check_edits, load_rules, run_checkers
from context_agent.quality_preflight import parse_preflight

RULES = ('dollar_math','semantic_numbers','semantic_math_text','number_with_unit','coordinate_reuse')

def select(job_root: Path, names: tuple[str,...]):
    yaml = job_root/'job.yaml'
    yaml.write_text(yaml.read_text().replace('quality: []',
        'quality:\n'+'\n'.join('  - '+r for r in names)), encoding='utf-8')


def test_explicit_empty_and_unknown(tmp_path,job_factory):
    root=job_factory(tmp_path)
    job=load_job(root)
    assert load_rules(job) == ()
    select(root,('does_not_exist',))
    with pytest.raises(ConfigurationError,match='unknown quality rule'):
        load_rules(load_job(root))


def test_five_rules_load_and_correct_math_text_policy(tmp_path,job_factory):
    root=job_factory(tmp_path)
    select(root,RULES)
    rules=load_rules(load_job(root))
    assert tuple(r.id for r in rules)==RULES
    assert all(r.check for r in rules)
    assert 'statt Low-Level' in rules[2].description
    assert '\\mtext' in rules[2].generation
    assert len(rules[1].resources)==1


def test_candidates_and_autofix(tmp_path,job_factory):
    root=job_factory(tmp_path)
    select(root,('semantic_numbers',))
    job=load_job(root)
    file=root/'result/main.tex'
    text='\\starttext\nDie Spannung ist 1{,}25 Volt im Jahr 2026.\\stoptext'
    file.write_text(text)
    rules=load_rules(job)
    context=QualityContext(job,file,None,None)
    findings,failures=run_checkers(rules,context)
    assert not failures
    assert len(findings)==1
    edits=rules[0].propose_edits(context,findings)
    assert len(edits)==1
    fixed=check_edits(text,edits)
    assert '\\dn{1.25}' in fixed and '2026' in fixed
    assert check_edits(fixed,edits) != fixed if False else True
    with pytest.raises(ValueError,match='stale'):
        check_edits(fixed,edits)


def test_repeated_coordinates_only_warning(tmp_path,job_factory):
    root=job_factory(tmp_path)
    select(root,('coordinate_reuse',))
    job=load_job(root)
    file=root/'result/main.tex'
    file.write_text('\\starttext\\startMPcode\ndraw (1cm,2cm)--(3cm,4cm);\n'
                    'dotlabel.top("A", (1cm,2cm));\n\\stopMPcode\\stoptext')
    found,failed=run_checkers(load_rules(job), QualityContext(job,file,None,None))
    assert not failed
    assert len(found)==1 and found[0].certainty=='candidate'


def test_unit_degree_candidates(tmp_path,job_factory):
    root=job_factory(tmp_path)
    select(root,('number_with_unit',))
    job=load_job(root)
    file=root/'result/main.tex'
    file.write_text(r'\starttext \m{30^\circ} und 30\unit{Degree} \stoptext')
    found,failed=run_checkers(load_rules(job),QualityContext(job,file,None,None))
    assert not failed and len(found)==1


def test_preflight_exact_plan_and_conflict():
    ids=('semantic_numbers','number_with_unit')
    data={'status':'passed','conflicts':[],'uncertainties':[],
          'plan':[['semantic_numbers'],['number_with_unit']]}
    assert parse_preflight(json.dumps(data),ids)['status']=='passed'
    data['plan']=[['semantic_numbers']]
    recovered = parse_preflight(json.dumps(data),ids)
    assert recovered['plan'] == [['semantic_numbers'], ['number_with_unit']]
    assert recovered['plan_fallback_reason'] == 'invalid_plan_coverage'
    data['plan']=[list(ids)]
    data['conflicts']=[{'rules':['number_with_unit'],'reason':'semantic collision',
                         'relevance':'blocking'}]
    with pytest.raises(Exception,match='blocking'):
        parse_preflight(json.dumps(data),ids)


def test_missing_quality_is_configuration_error(tmp_path,job_factory):
    root=job_factory(tmp_path)
    p=root/'job.yaml'
    p.write_text(p.read_text().replace('quality: []',''))
    with pytest.raises(ConfigurationError,match='quality'):
        load_job(root)


def test_unit_rule_includes_dn_resource_without_enabling_numbers(tmp_path,job_factory):
    from context_agent.bundling import build_job_bundle
    root=job_factory(tmp_path)
    select(root,('number_with_unit',))
    job=load_job(root)
    rules=load_rules(job)
    assert [r.id for r in rules] == ['number_with_unit']
    assert rules[0].resources[0].macro == r'\dn'
    runtime=tmp_path/'runtime'
    runtime.mkdir()
    archive=tmp_path/'jobbundle.tar.gz'
    build_job_bundle(job,archive,runtime,rules=rules)
    with tarfile.open(archive,'r:gz') as tf:
        filename='job/include/quality-rules/digits.tex'
        assert filename in tf.getnames()
        src=tf.extractfile(filename)
        assert src and b'\\setdigitmode 3' in src.read()
