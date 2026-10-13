import json
import subprocess
import tarfile
from pathlib import Path

from context_agent.bundling import build_job_bundle
from context_agent.job import load_job


def test_bundle_contains_job_runtime_and_manifest(tmp_path: Path, job_factory) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path)
    job = load_job(job_root)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "bootstrap-context.sh").write_text("#!/bin/sh\n")
    destination = tmp_path / "bundle.tar.gz"
    build_job_bundle(job, destination, runtime)

    with tarfile.open(destination, "r:gz") as archive:
        names = set(archive.getnames())
        assert "job/job.yaml" in names
        assert archive.getmember("job/include").isdir()
        assert archive.getmember("job/result").isdir()
        assert "job/result/main.tex" not in names
        assert "runtime/bootstrap-context.sh" in names
        manifest_file = archive.extractfile("agent-manifest.json")
        assert manifest_file is not None
        manifest = json.load(manifest_file)
        assert manifest["template"] == "job/template/template.tex"


def test_empty_include_directory_survives_extraction_and_snapshot(
    tmp_path: Path, job_factory,
) -> None:  # type: ignore[no-untyped-def]
    job_root = job_factory(tmp_path)
    job = load_job(job_root)
    assert not any(job.include_dir.iterdir())
    assert not any(job.result_dir.iterdir())

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    collector = (Path(__file__).resolve().parents[1] / "src" / "context_agent"
                 / "resources" / "runtime" / "collect-includes.sh")
    (runtime / "collect-includes.sh").write_bytes(collector.read_bytes())

    destination = tmp_path / "bundle.tar.gz"
    build_job_bundle(job, destination, runtime)
    extracted = tmp_path / "unpacked"
    extracted.mkdir()
    with tarfile.open(destination, "r:gz") as archive:
        archive.extractall(extracted, filter="data")

    assert (extracted / "job/include").is_dir()
    assert (extracted / "job/result").is_dir()
    subprocess.run(
        ["bash", str(extracted / "runtime/collect-includes.sh"), str(extracted / "job")],
        check=True, capture_output=True, text=True,
    )
    snapshot = extracted / "job/result/include-snapshot.tar.gz"
    assert snapshot.is_file()
    with tarfile.open(snapshot, "r:gz") as archive:
        assert archive.getmember("include").isdir()
