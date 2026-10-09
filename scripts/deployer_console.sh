#!/usr/bin/env bash
# Déploie la console Kaldera (Dockerfile racine) sur Cloud Run, branchée sur un partenaire.
#
#   PROJET=<id-du-projet-gcp> PARTENAIRE_URL=<url> PARTENAIRE_JETON=<jeton> \
#     ./scripts/deployer_console.sh
#
# PARTENAIRE_URL et PARTENAIRE_JETON sont ceux qu'affiche scripts/deployer_partenaire.sh.
# Variables facultatives : REGION (europe-west9), SERVICE (kaldera-console).
set -euo pipefail

PROJET="${PROJET:?indiquez PROJET=<id du projet GCP>}"
REGION="${REGION:-europe-west9}"
SERVICE="${SERVICE:-kaldera-console}"
PARTENAIRE_URL="${PARTENAIRE_URL:?indiquez PARTENAIRE_URL=<url du partenaire>}"
PARTENAIRE_JETON="${PARTENAIRE_JETON:?indiquez PARTENAIRE_JETON=<jeton du partenaire>}"
DEPOT="${DEPOT:-kaldera}"
IMAGE="$REGION-docker.pkg.dev/$PROJET/$DEPOT/$SERVICE:$(date +%Y%m%d-%H%M%S)"

# Le contexte de construction est la racine du dépôt (Dockerfile, pyproject.toml, src, eval).
cd "$(dirname "$0")/.."

echo "== Activation des API (Cloud Run, Artifact Registry)"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com --project "$PROJET"

echo "== Dépôt d'images $DEPOT ($REGION)"
gcloud artifacts repositories describe "$DEPOT" --location "$REGION" --project "$PROJET" \
  >/dev/null 2>&1 || gcloud artifacts repositories create "$DEPOT" --repository-format docker \
  --location "$REGION" --project "$PROJET" --description "Images Kaldera" --quiet
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet >/dev/null

echo "== Construction et envoi de l'image (en local : aucun droit Cloud Build requis)"
docker build -q -t "$IMAGE" .
docker push -q "$IMAGE"

echo "== Déploiement sur Cloud Run ($REGION)"
# Cloud Run fournit PORT (8080), sur lequel l'image écoute. Le jeton reste côté serveur.
gcloud run deploy "$SERVICE" --image "$IMAGE" \
  --project "$PROJET" --region "$REGION" \
  --allow-unauthenticated --memory 512Mi \
  --set-env-vars "PARTENAIRE_URL=$PARTENAIRE_URL,PARTENAIRE_JETON=$PARTENAIRE_JETON" --quiet

URL=$(gcloud run services describe "$SERVICE" --project "$PROJET" --region "$REGION" \
  --format 'value(status.url)')

echo "== Contrôle"
SANTE=$(curl -fsS --max-time 30 "$URL/api/sante")
echo "$SANTE"
echo
echo "Console déployée : $URL"
case "$SANTE" in
  *'"partenaire":"en ligne"'*) echo "Partenaire joignable depuis la console : $PARTENAIRE_URL" ;;
  *)
    echo "Attention : la console ne joint pas le partenaire ($PARTENAIRE_URL)." >&2
    exit 1
    ;;
esac
