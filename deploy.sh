#!/usr/bin/env bash
# deploy.sh — Build and deploy the Lambda zip package.
#
# Usage:
#   bash deploy.sh
#
# Environment variables (optional — override defaults):
#   LAMBDA_FUNCTION_NAME  Name of the target Lambda function (default: clean-grocery-bot)
#   AWS_REGION            AWS region (default: us-east-1)
#
set -euo pipefail

FUNCTION_NAME="${LAMBDA_FUNCTION_NAME:-clean-grocery-bot}"
REGION="${AWS_REGION:-us-east-1}"
BUILD_DIR="build"
ZIP_FILE="lambda-package.zip"

echo "==> Cleaning previous build..."
rm -rf "${BUILD_DIR}" "${ZIP_FILE}"
mkdir -p "${BUILD_DIR}"

echo "==> Exporting runtime dependencies (excluding boto3 — provided by Lambda)..."
uv export \
    --no-dev \
    --no-hashes \
    --format requirements-txt \
    --output-file requirements.txt

# Install for the Lambda execution environment (Linux x86_64, Python 3.12)
pip install \
    --quiet \
    --requirement requirements.txt \
    --target "${BUILD_DIR}" \
    --platform manylinux2014_x86_64 \
    --python-version 3.12 \
    --only-binary=:all: \
    --no-deps \
    --upgrade \
    || pip install \
        --quiet \
        --requirement requirements.txt \
        --target "${BUILD_DIR}"

# Remove boto3 and botocore — Lambda runtime provides them (~50 MB saved)
rm -rf \
    "${BUILD_DIR}/boto3" \
    "${BUILD_DIR}/boto3-"* \
    "${BUILD_DIR}/botocore" \
    "${BUILD_DIR}/botocore-"* \
    "${BUILD_DIR}/s3transfer" \
    "${BUILD_DIR}/s3transfer-"* \
    "${BUILD_DIR}/jmespath" \
    "${BUILD_DIR}/jmespath-"* 2>/dev/null || true

echo "==> Copying source package..."
cp -r src/clean_grocery_bot "${BUILD_DIR}/"

echo "==> Copying dietary_preference_config.json..."
cp dietary_preference_config.json "${BUILD_DIR}/"

echo "==> Creating zip archive..."
(cd "${BUILD_DIR}" && zip -qr "../${ZIP_FILE}" . --exclude '*.pyc' --exclude '*/__pycache__/*')

ZIP_SIZE=$(du -sh "${ZIP_FILE}" | cut -f1)
echo "==> Package size: ${ZIP_SIZE}"

echo "==> Deploying to Lambda function '${FUNCTION_NAME}' in ${REGION}..."
aws lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --zip-file "fileb://${ZIP_FILE}" \
    --region "${REGION}" \
    --output text \
    --query 'FunctionArn'

echo "==> Cleaning up..."
rm -rf "${BUILD_DIR}" requirements.txt

echo "==> Done! '${FUNCTION_NAME}' deployed successfully."
