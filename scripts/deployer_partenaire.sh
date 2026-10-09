#!/usr/bin/env bash
# Déploie le partenaire anti-fraude (partenaire_antifraude/) sur Cloud Run.
#
#   PROJET=<id-du-projet-gcp> ./scripts/deployer_partenaire.sh
#
# L'image est construite en local (Docker) puis poussée dans Artifact Registry : aucune
# dépendance aux droits du compte de service de Cloud Build.
# Variables facultatives : REGION (europe-west9), SERVICE (partenaire-antifraude),
# PARTENAIRE_JETON (généré s'il est absent).
set -euo pipefail

PROJET="${PROJET:?indiquez PROJET=<id du projet GCP>}"
REGION="${REGION:-europe-west9}"
SERVICE="${SERVICE:-partenaire-antifraude}"
DEPOT="${DEPOT:-kaldera}"
JETON="${PARTENAIRE_JETON:-$(python -c 'import secrets; print(secrets.token_urlsafe(32))')}"
IMAGE="$REGION-docker.pkg.dev/$PROJET/$DEPOT/$SERVICE:$(date +%Y%m%d-%H%M%S)"

echo "== Activation des API (Cloud Run, Artifact Registry)"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com --project "$PROJET"

echo "== Dépôt d'images $DEPOT ($REGION)"
gcloud artifacts repositories describe "$DEPOT" --location "$REGION" --project "$PROJET" \
  >/dev/null 2>&1 || gcloud artifacts repositories create "$DEPOT" --repository-format docker \
  --location "$REGION" --project "$PROJET" --description "Images Kaldera" --quiet
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet >/dev/null

echo "== Construction et envoi de l'image"
docker build -q -t "$IMAGE" partenaire_antifraude
docker push -q "$IMAGE"

echo "== Déploiement sur Cloud Run"
# --max-instances 1 : le registre « un seul appel par dossier » vit en mémoire.
gcloud run deploy "$SERVICE" --image "$IMAGE" \
  --project "$PROJET" --region "$REGION" \
  --allow-unauthenticated --max-instances 1 --memory 256Mi \
  --set-env-vars "PARTENAIRE_JETON=$JETON" --quiet

URL=$(gcloud run services describe "$SERVICE" --project "$PROJET" --region "$REGION" \
  --format 'value(status.url)')
gcloud run services update "$SERVICE" --project "$PROJET" --region "$REGION" \
  --update-env-vars "URL_PUBLIQUE=$URL" --quiet

echo "== Contrôle"
curl -fs "$URL/health" && echo
echo
echo "Partenaire déployé : $URL"
echo "Pour brancher Kaldera :"
echo "  PARTENAIRE_URL=$URL"
echo "  PARTENAIRE_JETON=$JETON"
