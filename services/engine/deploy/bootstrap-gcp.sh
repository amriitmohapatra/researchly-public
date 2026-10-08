#!/usr/bin/env bash
# One-time Google Cloud setup for the Researchly engine (PLAN.md S1).
#
# Run it in Google Cloud Shell (the ">_" button at console.cloud.google.com),
# which already has gcloud and is signed in as you:
#
#     bash bootstrap-gcp.sh YOUR_PROJECT_ID
#
# It is safe to run twice: every step checks before it creates.
#
# What it creates (all in region asia-southeast1 / Singapore, decision D3):
#   - Artifact Registry repo "researchly" for container images
#   - service account researchly-engine   the engine runs as this; it is
#                                         granted NO roles: it reads and
#                                         writes nothing in your project
#   - service account researchly-deployer GitHub Actions deploys as this
#   - Workload Identity Federation        lets GitHub Actions from
#                                         amriitmohapatra/Researchly ONLY
#                                         act as the deployer, with
#                                         short-lived tokens, no key files
#
# No keys, passwords or secrets are created or printed. The three values it
# prints at the end are identifiers, not credentials: paste them into the
# repository's Actions *variables* (not secrets).
set -euo pipefail

PROJECT_ID="${1:?usage: bash bootstrap-gcp.sh YOUR_PROJECT_ID}"
REGION="asia-southeast1"
GITHUB_REPO="amriitmohapatra/Researchly"
AR_REPO="researchly"
POOL="github"
PROVIDER="github-oidc"
RUNTIME_SA="researchly-engine@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_SA="researchly-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

say() { printf '\n== %s\n' "$*"; }

say "Using project ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

say "Enabling APIs (takes a minute the first time)"
gcloud services enable \
  run.googleapis.com artifactregistry.googleapis.com iam.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com cloudresourcemanager.googleapis.com

say "Artifact Registry repository ${AR_REPO} (${REGION})"
if ! gcloud artifacts repositories describe "${AR_REPO}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${AR_REPO}" --repository-format=docker \
    --location="${REGION}" --description="Researchly container images"
fi

make_sa() {  # name, description
  if ! gcloud iam service-accounts describe "$1@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$1" --display-name="$2"
  fi
}
say "Service accounts"
make_sa researchly-engine   "Researchly engine runtime (no roles granted)"
make_sa researchly-deployer "Researchly deployer (GitHub Actions)"

say "Deployer permissions (only what a deploy needs)"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${DEPLOY_SA}" --role="roles/run.admin" --condition=None >/dev/null
gcloud artifacts repositories add-iam-policy-binding "${AR_REPO}" --location="${REGION}" \
  --member="serviceAccount:${DEPLOY_SA}" --role="roles/artifactregistry.writer" >/dev/null
# The deployer may launch the engine AS the runtime account, and nothing else.
gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA}" \
  --member="serviceAccount:${DEPLOY_SA}" --role="roles/iam.serviceAccountUser" >/dev/null

say "Workload Identity Federation for ${GITHUB_REPO}"
if ! gcloud iam workload-identity-pools describe "${POOL}" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "${POOL}" --location=global \
    --display-name="GitHub Actions"
fi
if ! gcloud iam workload-identity-pools providers describe "${PROVIDER}" --location=global \
     --workload-identity-pool="${POOL}" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "${PROVIDER}" --location=global \
    --workload-identity-pool="${POOL}" --display-name="GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}'"
fi
gcloud iam service-accounts add-iam-policy-binding "${DEPLOY_SA}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${GITHUB_REPO}" >/dev/null

cat <<DONE

==========================================================================
Done. Add these three as repository VARIABLES (not secrets) at
https://github.com/${GITHUB_REPO}/settings/variables/actions

  GCP_PROJECT_ID    ${PROJECT_ID}
  GCP_WIF_PROVIDER  projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}
  GCP_DEPLOY_SA     ${DEPLOY_SA}

Then set a budget alert (Billing -> Budgets & alerts) at e.g. USD 10/month.
The engine is capped at 2 instances, so cost stays near zero at student
scale, but an alert is the backstop.
==========================================================================
DONE
