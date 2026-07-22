"""Artifact storage — real AWS S3 in production, local mock for dev/tests.

Provider is chosen by TRACERAG_STORAGE_PROVIDER:
  * 's3'    -> boto3 upload_file/download_file (multipart-aware for big .lbug files),
               bucket from TRACERAG_S3_BUCKET, credentials/region from the standard
               AWS_* env vars. URIs are ``s3://<bucket>/<key>``.
  * 'local' -> file copy under TENANT_DATA_DIR/s3_mock/ (the default; keeps dev and
               the offline tests hermetic). URIs are ``s3mock://<key>``.

get_artifact dispatches on the URI scheme, so an artifact recorded as ``s3://…``
is always fetched via boto3 even if the process default later changes.
"""

import hashlib
import os
import shutil
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent

# Root for all tenant/pod local state. Override with TENANT_DATA_DIR.
TENANT_DATA_DIR = Path(os.getenv("TENANT_DATA_DIR", _BACKEND_DIR / "tenant_data"))
S3_MOCK_DIR = TENANT_DATA_DIR / "s3_mock"          # stands in for the S3 bucket
BUILD_DIR = TENANT_DATA_DIR / "build"              # worker compile scratch
POD_CACHE_DIR = TENANT_DATA_DIR / "pods"           # per-pod downloaded artifacts

ARTIFACT_PREFIX = os.getenv("TRACERAG_ARTIFACT_S3_PREFIX", "artifacts")

STORAGE_PROVIDER = os.getenv("TRACERAG_STORAGE_PROVIDER", "local").lower()
S3_BUCKET = os.getenv("TRACERAG_S3_BUCKET")
S3_REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")

_MOCK_SCHEME = "s3mock://"
_S3_SCHEME = "s3://"

_s3 = None


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _s3_client():
    """Lazily build a boto3 S3 client (reads AWS_* env vars). Imported only when
    the S3 provider is actually used, so local/dev never needs boto3 installed."""
    global _s3
    if _s3 is None:
        import boto3

        if not S3_BUCKET:
            raise RuntimeError("TRACERAG_S3_BUCKET must be set for the 's3' provider.")
        _s3 = boto3.client("s3", region_name=S3_REGION)
    return _s3


# ---- local scratch paths (used by both providers) --------------------------
def build_dir(org_id: str) -> Path:
    return _ensure(BUILD_DIR / org_id)


def pod_artifact_path(pod_id: str, org_id: str, version: int) -> Path:
    return _ensure(POD_CACHE_DIR / pod_id / org_id) / f"v{version}.lbug"


def artifact_key(org_id: str, version: int) -> str:
    """The object key (path within the bucket) for an org's artifact version."""
    return f"{ARTIFACT_PREFIX}/{org_id}/v{version}.lbug"


# ---- upload / download -----------------------------------------------------
def put_artifact(local_path: Path | str, key: str) -> str:
    """Upload a local file to the artifact store; return its URI.

    S3 uses upload_file (multipart under the hood for large artifacts); local
    copies into the mock bucket dir."""
    if STORAGE_PROVIDER == "s3":
        _s3_client().upload_file(str(local_path), S3_BUCKET, key)
        return f"{_S3_SCHEME}{S3_BUCKET}/{key}"
    dest = S3_MOCK_DIR / key
    _ensure(dest.parent)
    shutil.copyfile(local_path, dest)
    return f"{_MOCK_SCHEME}{key}"


def get_artifact(s3_uri: str, dest_path: Path | str) -> Path:
    """Download an artifact by URI to dest_path; return dest_path. Dispatches on
    the URI scheme, not the current provider."""
    dest = Path(dest_path)
    _ensure(dest.parent)

    if s3_uri.startswith(_S3_SCHEME):
        bucket, _, key = s3_uri[len(_S3_SCHEME):].partition("/")
        _s3_client().download_file(bucket, key, str(dest))
        return dest

    if s3_uri.startswith(_MOCK_SCHEME):
        src = S3_MOCK_DIR / s3_uri[len(_MOCK_SCHEME):]
        if not src.exists():
            raise FileNotFoundError(f"artifact missing in mock bucket: {src}")
        shutil.copyfile(src, dest)
        return dest

    raise ValueError(f"unrecognized artifact URI scheme: {s3_uri!r}")


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
