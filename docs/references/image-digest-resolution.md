# Image Digest Resolution

How one built image surfaces as different digests across Artifact Registry, CI, and Cloud Run — and how to verify provenance end to end.

## The Three Digests

A single `docker buildx` push from CI produces three content-addressed objects describing the image, plus a shared cache artifact (see [The Registry Cache Artifact](#the-registry-cache-artifact)):

| Object | What it is | Where you see it |
|---|---|---|
| **Image index** ([manifest list](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/about-container-images)) | The envelope buildx pushes. Contains pointers to the platform image and the attestation | Registry tags (`{sha}`, `latest`, `{version}`), `resolve-image-digest.yml` output, Terraform `docker_image`, Cloud Run **service** spec |
| **Platform image manifest** | The actual runnable `linux/amd64` image | Cloud Run **revision** spec (`spec.containers[0].image`) |
| **Attestation manifest** | BuildKit provenance metadata (SLSA), platform `unknown/unknown` | Inside the index only; annotated `vnd.docker.reference.type: attestation-manifest` |

Two consequences follow:

1. **The index exists even for single-platform builds.** Provenance attestations are [added to images by default](https://docs.docker.com/build/metadata/attestations/) by buildx, and attestations are [stored as manifest objects in the image index](https://docs.docker.com/build/metadata/attestations/attestation-storage/) — so the OCI index wrapper appears around even a lone `linux/amd64` image.
2. **The tag digest never matches the revision digest.** Two documented behaviors compose here: Cloud Run resolves the image to a digest when it creates a revision ([Revision API reference](https://docs.cloud.google.com/run/docs/reference/rest/v1/namespaces.revisions): "ImageDigest holds the resolved digest for the image specified within .Spec.Container.Image. The digest is resolved during the creation of Revision"), and container runtimes [select the platform-matching image from an image index](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/about-container-images). The digest recorded on a revision is therefore the `linux/amd64` child, not the index the tag names — confirm against your own service with the commands below. A mismatch between tag digest and revision digest is expected, not a deployment integrity problem.

> [!NOTE]
> The Artifact Registry console may show a third "image" with platform `unknown/unknown` under the same upload. That is the attestation manifest, not a mis-built artifact — the [attestation storage spec](https://docs.docker.com/build/metadata/attestations/attestation-storage/) sets `platform` to `unknown/unknown` and annotates the manifest with `vnd.docker.reference.digest` pointing at the image it attests.

## The Registry Cache Artifact

The build workflow also pushes BuildKit layer cache to the same image name under the `buildcache` tag (`cache-to: type=registry,...:buildcache,mode=max` in `docker-build.yml`). This is an OCI image manifest holding cached layers for every build stage — `mode=max` includes intermediate builder-stage layers that never ship in the runtime image.

Properties that distinguish it from the image objects above:

- Overwritten on every build (one `buildcache` tag per image name, not per commit)
- Never deployed — Cloud Run never references it; it exists only for `cache-from` on subsequent builds
- Why fully cached rebuilds reproduce byte-identical digests: a rerun on the same source pulls every layer from this cache, re-executes nothing, and exports the same manifests

When browsing the repository, expect it alongside the per-build objects.

## Resolving the Chain

Trace tag → index → platform image with these commands. Authenticate Docker once if needed:

```bash
gcloud auth configure-docker ${LOCATION}-docker.pkg.dev
```

**1. Tag → index digest** (what CI resolves and Terraform deploys):

```bash
gcloud artifacts docker images describe \
  "${LOCATION}-docker.pkg.dev/${PROJECT}/${REPO}/${IMAGE}:${TAG}" \
  --format "value(image_summary.digest)"
```

**2. Index → children** (platform image + attestation):

```bash
docker buildx imagetools inspect \
  "${LOCATION}-docker.pkg.dev/${PROJECT}/${REPO}/${IMAGE}@${INDEX_DIGEST}"
```

The output lists the `linux/amd64` manifest digest and an `unknown/unknown` attestation manifest whose `vnd.docker.reference.digest` annotation points back at the platform image.

**3. Cloud Run service → deployed index digest:**

```bash
gcloud run services describe ${SERVICE} --region ${LOCATION} \
  --format "value(spec.template.spec.containers[0].image)"
```

**4. Cloud Run revision → running platform digest:**

```bash
gcloud run revisions describe ${REVISION} --region ${LOCATION} \
  --format "value(spec.containers[0].image)"
```

**5. CI build log → both digests at export time** (proves what a workflow run produced):

```bash
gh run view ${RUN_ID} --log | grep -E "exporting manifest|exporting manifest list|pushing manifest"
```

Look for `exporting manifest sha256:...` (platform image) followed by `exporting manifest list sha256:...` (index). A rerun whose layers all report `CACHED` reproduces both digests byte-identically.

> [!TIP]
> The repo also bundles this procedure as the `verify-image-provenance` agent skill, usable with your AI coding assistant of choice.

## Console Paths

- **Artifact Registry:** Console → Artifact Registry → Repositories → `{agent_name}-{env}` → image name. The digest list shows the index (carries the tags) and its children. Click a digest → Manifest tab for the raw JSON.
- **Cloud Run service (deployed index):** Console → Cloud Run → service → Revisions tab → "Image URL" column header area shows the service-level image; YAML view shows `spec.template.spec.containers[0].image`.
- **Cloud Run revision (running platform image):** Console → Cloud Run → service → Revisions tab → select revision → Containers section → "Image" shows the digest-qualified URI Cloud Run recorded at import.
- **Build provenance:** GitHub → Actions → CI/CD Pipeline run → Build Docker Image job → "Build and Push to Artifact Registry" step log.

## Worked Example

From the v0.16.0 release (commit `4ae72ab`):

```text
Tags 4ae72ab, latest, v0.16.0
  → index sha256:87d5625f...          (what resolve-image-digest passed to Terraform)
      ├── linux/amd64 manifest sha256:5cc32590...   (what revisions record)
      └── attestation manifest sha256:95cb7bf4...   (provenance for 5cc32590)
```

Revisions `00065` and `00066` both record `5cc32590...` — two deploy attempts of the same index resolve to the same platform image. During the incident that motivated this doc, that equality is what proved a startup failure was transient infrastructure rather than a bad build: the byte-identical image failed its startup probe once and served cleanly on the rerun.

## Debugging With Digests

- **"The revision digest doesn't match what CI deployed"** — expected; compare the revision digest against the index's `linux/amd64` child (step 2 above), not against the tag.
- **"Did the rerun deploy the same image?"** — compare `spec.containers[0].image` across the two revisions. Revision image fields are immutable, so equality is proof. Corroborate with the build log: all-`CACHED` layers reproduce identical digests.
- **"Which commit produced the running image?"** — find the running revision's platform digest, locate its parent index (`docker buildx imagetools inspect` on each tagged index, or the Artifact Registry console child view), and read the index's `{sha}` tag.
- **"Is this `unknown/unknown` artifact a problem?"** — no; it is the provenance attestation. It never runs.

---

← [Back to References](README.md) | [Documentation](../README.md)
