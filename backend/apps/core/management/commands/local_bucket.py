"""Local review only: make sure the local bucket exists (and is empty with --empty)."""
import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--empty", action="store_true", help="delete every file in the bucket")

    def handle(self, *args, empty, **options):
        if settings.SETTINGS_MODULE != "vayu.settings.local":
            raise CommandError("local_bucket only runs with the local settings.")
        s3 = boto3.client("s3", endpoint_url=settings.S3_ENDPOINT_URL,
                          aws_access_key_id=settings.S3_ACCESS_KEY_ID,
                          aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
                          region_name=settings.S3_REGION)
        try:
            s3.create_bucket(Bucket=settings.S3_BUCKET)
            self.stdout.write(f"created bucket {settings.S3_BUCKET}")
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise
        if empty:
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=settings.S3_BUCKET):
                for o in page.get("Contents", []):
                    s3.delete_object(Bucket=settings.S3_BUCKET, Key=o["Key"])
            for u in s3.list_multipart_uploads(Bucket=settings.S3_BUCKET).get("Uploads", []):
                s3.abort_multipart_upload(Bucket=settings.S3_BUCKET, Key=u["Key"],
                                          UploadId=u["UploadId"])
            self.stdout.write("bucket emptied")
