#!/usr/bin/env bash
# deploy.sh — Build and deploy the Lambda zip package.
#
# Usage:
#   bash deploy.sh
#
# Environment variables (optional — override defaults):
#   LAMBDA_FUNCTION_NAME  Name of the target Lambda function (default: clean-grocery-bot)
#   AWS_REGION            AWS region (default: us-east-2)
#
set -euo pipefail

FUNCTION_NAME="${LAMBDA_FUNCTION_NAME:-clean-grocery-bot}"
REGION="${AWS_REGION:-us-east-2}"
BUILD_DIR="build"
ZIP_FILE="lambda-package.zip"

# Derive Lambda architecture from the build machine so packages and runtime always match.
# Lambda supports arm64 (Graviton) and x86_64.  Building on a different architecture
# than the Lambda target causes native extensions (e.g. pydantic_core) to fail at import.
_MACHINE=$(uname -m)
if [ "${_MACHINE}" = "aarch64" ] || [ "${_MACHINE}" = "arm64" ]; then
    LAMBDA_ARCH="arm64"
else
    LAMBDA_ARCH="x86_64"
fi
echo "==> Build machine: ${_MACHINE} → Lambda architecture: ${LAMBDA_ARCH}"

echo "==> Cleaning previous build..."
rm -rf "${BUILD_DIR}" "${ZIP_FILE}"
mkdir -p "${BUILD_DIR}"

echo "==> Exporting runtime dependencies (excluding boto3 — provided by Lambda)..."
uv export \
    --no-dev \
    --no-hashes \
    --format requirements-txt \
    --output-file requirements.txt

# Strip the editable self-install (-e .) — source is copied separately below.
grep -v '^-e ' requirements.txt > requirements-deps.txt

# Install dependencies for the Lambda execution environment.
# Architecture is derived from the build machine above, so packages always match the runtime.
uv pip install \
    --quiet \
    --requirement requirements-deps.txt \
    --target "${BUILD_DIR}" \
    --no-deps

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
python3 -c "
import zipfile, os
with zipfile.ZipFile('${ZIP_FILE}', 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk('${BUILD_DIR}'):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            if not f.endswith('.pyc'):
                path = os.path.join(root, f)
                zf.write(path, os.path.relpath(path, '${BUILD_DIR}'))
"

ZIP_SIZE=$(du -sh "${ZIP_FILE}" | cut -f1)
echo "==> Package size: ${ZIP_SIZE}"

echo "==> Deploying to Lambda function '${FUNCTION_NAME}' in ${REGION}..."
aws lambda update-function-code \
    --function-name "${FUNCTION_NAME}" \
    --zip-file "fileb://${ZIP_FILE}" \
    --architectures "${LAMBDA_ARCH}" \
    --region "${REGION}" \
    --output text \
    --query 'FunctionArn'

echo "==> Cleaning up..."
rm -rf "${BUILD_DIR}" requirements.txt requirements-deps.txt

echo "==> Done! '${FUNCTION_NAME}' deployed successfully."
