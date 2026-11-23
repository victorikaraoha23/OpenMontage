---
name: ltx2
description: AI video generation with LTX-2.3 22B — text-to-video and image-to-video clips. Use when generating video clips, animating images, creating b-roll, animated backgrounds, or motion content.
---

# LTX-2.3 Video Generation

OpenMontage integrates LTX-2.3 through the authenticated Modal endpoint described in
[`docker/modal_ltx2/README.md`](../../../docker/modal_ltx2/README.md). The endpoint
uses the official LTX-2.3 distilled pipeline, an A100-80GB GPU, and a persistent
Modal Volume for model weights.

## Setup

Follow the deployment guide exactly. Required local environment variables:

- `MODAL_LTX2_ENDPOINT_URL`
- `MODAL_LTX2_API_TOKEN`

The corresponding Modal secret `openmontage-ltx2` must contain `HF_TOKEN` and
`OPENMONTAGE_API_TOKEN`. Never place tokens in source control.

## OpenMontage integration

The provider is called through the existing video tool/provider routing and
`tools/video/_shared.py::generate_ltx_modal_video`. There is no standalone
`tools/ltx2.py` command-line interface in this repository. Do not invent or invoke
one. Use the normal OpenMontage video-generation workflow.

The provider defaults to vertical 576x1024, 121 frames, and 24 FPS. The final
composition stage must conform output to the delivery profile (9:16, 1080x1920,
30 FPS). LTX generation clips are source assets, not final deliverables.

## Model and license requirements

- LTX checkpoint: `Lightricks/LTX-2.3`, distilled 1.1 checkpoint.
- Text encoder: `google/gemma-3-12b-it`.
- Spatial upscaler: LTX-2.3 x2 1.1.
- Accept each model's applicable license and gated access requirements before
  deploying. The first request downloads tens of gigabytes and incurs storage/GPU cost.

## Important limitations

- The upstream distilled pipeline uses its fixed denoising schedule. A generic
  `steps` input does not tune its inference steps.
- Reference-image URLs must be HTTPS, resolve to public IP addresses, and may not
  redirect. Local reference images are uploaded as base64 (20 MiB maximum).
- The endpoint requires a bearer token and returns MP4 data in base64 JSON.
