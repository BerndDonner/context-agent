import json
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
        assert "job/result" not in names
        assert "runtime/bootstrap-context.sh" in names
        manifest_file = archive.extractfile("agent-manifest.json")
        assert manifest_file is not None
        manifest = json.load(manifest_file)
        assert manifest["template"] == "job/template/template.tex"
