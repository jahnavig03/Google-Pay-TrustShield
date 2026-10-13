# infra/ — Cloud Build + gcloud bootstrap

**Owner: Hitesh.** Everything here is idempotent and takes `--dry-run`. Only `gcloud`, `bq` and
`gcloud storage` are used, never `gsutil`.

Defaults: `GCP_PROJECT_ID=qualified-sun-511214-t1`, `GCP_REGION=asia-south1`. Both are read from
the environment first, then the repo-root `.env`, then those defaults, and both can be overridden
per run with `--project` / `--region`.

## Run order

```bash
gcloud auth login
gcloud config set project qualified-sun-511214-t1

bash infra/enable-apis.sh --dry-run     # read it, then run it for real
bash infra/enable-apis.sh

bash infra/bootstrap.sh --dry-run       # every line should say [exists] once set up
bash infra/bootstrap.sh
```

`--dry-run` prints `[exists]` / `[create]` per resource and the exact command it would run, and
changes nothing.

### `enable-apis.sh`

Enables the 16 APIs TrustShield uses: Vertex AI, BigQuery, Pub/Sub, Cloud Run, Firestore,
Document AI, Discovery Engine (Vertex AI Search), Cloud Build, Artifact Registry, Cloud Storage,
Secret Manager, Logging, Monitoring, Firebase, Firebase Hosting and Identity Toolkit. Already
enabled APIs are skipped, so a second run is a no-op.

### `bootstrap.sh`

Creates, only if missing:

| Resource | Name |
| --- | --- |
| Cloud Storage buckets | `<project>-uploads`, `<project>-policies`, `<project>-datasets` |
| Firestore | `(default)`, native mode, `asia-south1` |
| BigQuery dataset | `trustshield` (`BQ_DATASET` overrides) |
| Pub/Sub topics | `payments`, `alerts`, `cases`, `reports` |
| Artifact Registry | docker repo `trustshield` in `asia-south1` |

Buckets are created with uniform bucket-level access and public access prevention. Firestore's
location is fixed at creation and cannot be changed afterwards.

## `cloudbuild.yaml` (repo root)

`test` → `build` → `push` → `deploy` → `smoke`.

1. **test** — `python:3.11-slim`, `TRUSTSHIELD_MODE=mock`, no credentials and no emulators. Runs
   pytest in `shared/contracts`, `services/agents` and `services/gateway`. A failure here stops
   the build before anything is pushed.
2. **build** — `docker build -f services/gateway/Dockerfile .` from the repo root, because the
   image needs `shared/contracts` and `services/agents` too.
3. **push** — `asia-south1-docker.pkg.dev/$PROJECT_ID/trustshield/gateway:$SHORT_SHA` and
   `:latest`.
4. **deploy** — `gcloud run deploy trustshield-gateway --region asia-south1
   --allow-unauthenticated --min-instances 0 --max-instances 2`, with
   `TRUSTSHIELD_MODE=gcp,GCP_PROJECT_ID,GCP_REGION,GEMINI_FAST_MODEL,GEMINI_FAST_THINKING_BUDGET`.
5. **smoke** — curls the deployed `/health` and fails the build if it does not answer.

Substitutions (`_REGION`, `_SERVICE`, `_MIN_INSTANCES`, `_MAX_INSTANCES`, `_GEMINI_FAST_MODEL`,
`_GEMINI_FAST_THINKING_BUDGET`) can be overridden on the trigger without editing the file.

Running it by hand needs a `SHORT_SHA`, which only a trigger sets automatically:

```bash
gcloud builds submit --config cloudbuild.yaml --substitutions=SHORT_SHA=manual .
```

## Connecting the Cloud Build trigger to GitHub

The repository is `jahnavig03/Google-Pay-TrustShield`. **Jahnavi owns it and has to approve the
Cloud Build GitHub app before step 2 will work — ask her first.**

1. Cloud Build → **Repositories** → the **2nd gen** tab → **Link repository**.
2. Source **GitHub**, then **Authenticate**. Install the Google Cloud Build app on
   `jahnavig03/Google-Pay-TrustShield` (Jahnavi approves this), pick the repo and link it.
3. Cloud Build → **Triggers** → **Create trigger**:
   - Name `deploy-gateway-main`, region `asia-south1`
   - Event **Push to a branch**, branch `^main$`
   - Source: the 2nd-gen repository linked above
   - Configuration **Cloud Build configuration file**, location `/cloudbuild.yaml`
4. Grant the build service account the roles it needs (it is
   `<project-number>-compute@developer.gserviceaccount.com` unless the trigger names another):
   `roles/run.admin`, `roles/artifactregistry.writer`, `roles/iam.serviceAccountUser`,
   `roles/logging.logWriter`.
5. **Run trigger** once by hand, then watch the build log.

## After the first deploy

The fixture file wraps the payment in a `"request"` key, so send just that object:

```bash
URL=$(gcloud run services describe trustshield-gateway --region asia-south1 --format='value(status.url)')
curl "$URL/health"

python3 -c 'import json;print(json.dumps(json.load(open("shared/contracts/fixtures/demo1_payment_85k.json"))["request"]))' \
  | curl -X POST "$URL/api/v1/payment-risk/evaluate" \
      -H 'Content-Type: application/json' -H 'X-Demo-Role: customer' -d @-
```

Expect `HOLD_AND_ESCALATE` with a non-empty `audit_id` and `case_id`, and a new document in the
Firestore `audit_log` collection. Post the URL in the team chat so Sameer can set
`VITE_API_BASE_URL`.

## Local emulators

`firebase.json` at the repo root configures the Firestore emulator on 8080, the Pub/Sub emulator
on 8085 and the emulator UI on 4000, with `singleProjectMode` on. `.firebaserc` points at
`qualified-sun-511214-t1`, and `firestore.rules` denies every client request: the gateway reaches
Firestore through the server SDK, which bypasses rules, so nothing should ever talk to Firestore
directly from a browser.

```bash
firebase emulators:start --only firestore
FIRESTORE_EMULATOR_HOST=localhost:8080 pytest     # in services/gateway
```

Change the port in `firebase.json` and in `.env` together if 8080 is taken.

### Java on a locked-down Mac

firebase-tools 15 needs Java 21+, and the Temurin `.pkg` installer needs admin rights that a
managed laptop may not grant. The `.pkg` is only an archive, so you can unpack it into your home
folder instead, with no admin at all:

```bash
pkgutil --expand-full ~/Downloads/OpenJDK*.pkg /tmp/jdkx
mkdir -p ~/Library/Java/JavaVirtualMachines
cp -R /tmp/jdkx/*/Payload/Library/Java/JavaVirtualMachines/*.jdk ~/Library/Java/JavaVirtualMachines/
java -version
```

macOS looks in `~/Library/Java/JavaVirtualMachines` automatically, so nothing else needs setting.
Deleting that folder undoes it. `npm install -g firebase-tools` needs no admin either when node
comes from nvm, because the global prefix is already inside your home directory.

## Cost rule

Team decision, no extra billing: `--min-instances 0` and `--max-instances 2` until judging.
Set `--min-instances 1` only on 17–18 Oct (override `_MIN_INSTANCES` on the trigger rather than
editing `cloudbuild.yaml`), and put it back to 0 afterwards. No Provisioned Throughput and no
reserved capacity anywhere.
