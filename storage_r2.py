"""
Cloudflare R2 storage (S3-compatible) for uploaded training files.

Why: storing file bytes directly in Postgres works but eats into the
database's storage quota fast (Neon's free tier is only 0.5GB) — a few
hundred PDFs will fill that up. R2's free tier is 10GB storage with
NO egress fees (unlike AWS S3), which comfortably fits this app's
actual usage pattern: files are written once and read back
occasionally for reprocessing, never served publicly.

Falls back to storing bytes directly in Postgres (the old behavior)
if R2 credentials aren't configured — so this is safe to deploy
without R2 set up yet.
"""

import os

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME")


def is_configured() -> bool:
    return all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME])


def _client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def upload_bytes(key: str, data: bytes) -> None:
    """key: e.g. 'org_uploads/<org_id>/<upload_id>_<filename>' — never
    made public; only ever read back by this app's own server code."""
    _client().put_object(Bucket=R2_BUCKET_NAME, Key=key, Body=data)


def download_bytes(key: str) -> bytes:
    resp = _client().get_object(Bucket=R2_BUCKET_NAME, Key=key)
    return resp["Body"].read()


def delete_object(key: str) -> None:
    _client().delete_object(Bucket=R2_BUCKET_NAME, Key=key)
