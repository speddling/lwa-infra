"""Render the pinned chart twice and verify the effective ArgoCD resources."""
import copy
import hashlib
from pathlib import Path
import subprocess
import tempfile
import time

import yaml


ROOT = Path(__file__).resolve().parents[2]


def identity(resource):
    return (resource["apiVersion"], resource["kind"], resource["metadata"].get("namespace"), resource["metadata"]["name"])


def validate():
    app = yaml.safe_load((ROOT / "kubernetes/apps/plane.yaml").read_text())["spec"]
    source, override_source = app["sources"]
    assert "source" not in app
    assert source["chart"] == "plane-ce" and source["targetRevision"] == "1.5.1"
    assert override_source["path"] == "kubernetes/plane-overrides"
    values = yaml.safe_load(source["helm"]["values"])
    version = values["planeVersion"]
    assert version == "v1.4.2"
    hook = yaml.safe_load((ROOT / override_source["path"] / "migrator.yaml").read_text())
    annotations = hook["metadata"]["annotations"]
    assert annotations["argocd.argoproj.io/hook"] == "Sync"
    assert annotations["argocd.argoproj.io/hook-delete-policy"] == "BeforeHookCreation"
    assert annotations["argocd.argoproj.io/sync-wave"] == "0"
    assert hook["spec"]["backoffLimit"] == 0
    container = hook["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == (
        "artifacts.plane.so/makeplane/plane-backend:" + version
        + "@sha256:90032ce088708889b60c00d491897916f4deb882facda27db59fd10fb68729ef"
    )
    assert container["command"][:2] == ["/bin/bash", "-ec"]
    assert "python manage.py migrate --check" in container["command"][2]
    assert "RespectIgnoreDifferences=true" in app["syncPolicy"]["syncOptions"]
    ignores = app["ignoreDifferences"]
    assert len(ignores) == 2
    assert ignores[1] == {"group": "apps", "kind": "Deployment", "namespace": "plane",
                          "jsonPointers": ["/spec/template/metadata/annotations/timestamp"]}
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        subprocess.run(["helm", "pull", "plane-ce", "--repo", source["repoURL"],
                        "--version", source["targetRevision"], "--destination", temp], check=True)
        chart = directory / "plane-ce-1.5.1.tgz"
        assert hashlib.sha256(chart.read_bytes()).hexdigest() == "251659b5bd94cfa7e336bcb719f457ca08c0f650ca346aca06399d05d1f2e1bb"
        value_file = directory / "values.yaml"
        value_file.write_text(source["helm"]["values"])
        renders = []
        for _ in range(2):
            result = subprocess.run(["helm", "template", "plane", str(chart), "-n", "plane",
                                     "-f", str(value_file)], check=True, capture_output=True, text=True)
            renders.append([r for r in yaml.safe_load_all(result.stdout) if r])
            time.sleep(1.1)
    effective = []
    for resources in renders:
        combined = {}
        for resource in resources:
            key = identity(resource)
            assert key not in combined
            combined[key] = copy.deepcopy(resource)
        original = combined[identity(hook)]
        old_container = original["spec"]["template"]["spec"]["containers"][0]
        assert old_container["envFrom"] == container["envFrom"]
        assert original["spec"]["template"]["spec"]["serviceAccountName"] == hook["spec"]["template"]["spec"]["serviceAccountName"]
        # ArgoCD's documented last-source-wins behavior replaces this exact Job.
        combined[identity(hook)] = hook
        for resource in combined.values():
            if resource["kind"] == "Deployment":
                if resource["metadata"]["name"] == "plane-api-wl":
                    assert resource["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"] == "1"
                template = resource["spec"]["template"]
                template["metadata"]["annotations"].pop("timestamp")
                for c in template["spec"]["containers"]:
                    assert c["image"].endswith(":" + version)
        effective.append(combined)
    assert renders[0] != renders[1], "Expected the upstream timestamp to differ"
    assert effective[0] == effective[1], "Unexpected reconciliation drift remains"
    print("Pinned chart, matching migrator, secret references and repeat-render stability passed")


if __name__ == "__main__":
    validate()
