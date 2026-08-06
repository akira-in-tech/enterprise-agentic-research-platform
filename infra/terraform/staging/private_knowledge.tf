resource "random_id" "document_bucket_suffix" {
  byte_length = 4
}

locals {
  private_knowledge_bedrock_actions = ["bedrock:InvokeModel"]
}

resource "aws_s3_bucket" "private_documents" {
  bucket        = "${local.name_prefix}-${random_id.document_bucket_suffix.hex}-documents"
  force_destroy = true

  tags = {
    Name = "${local.name_prefix}-private-documents"
  }
}

resource "aws_s3_bucket_public_access_block" "private_documents" {
  bucket = aws_s3_bucket.private_documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "private_documents" {
  bucket = aws_s3_bucket.private_documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "private_documents" {
  bucket = aws_s3_bucket.private_documents.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "private_documents" {
  bucket = aws_s3_bucket.private_documents.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.private_documents]
}

resource "aws_iam_role_policy" "ecs_task_private_knowledge" {
  name = "private-knowledge-access"
  role = aws_iam_role.ecs_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "InvokeTitanEmbeddings"
        Effect   = "Allow"
        Action   = local.private_knowledge_bedrock_actions
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
      },
      {
        Sid      = "ListPrivateDocuments"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.private_documents.arn
      },
      {
        Sid    = "ManagePrivateDocumentObjects"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = "${aws_s3_bucket.private_documents.arn}/*"
      },
    ]
  })
}
