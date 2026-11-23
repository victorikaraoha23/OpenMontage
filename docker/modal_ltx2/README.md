# OpenMontage LTX-2.3 on Modal

This optional deployment provides an authenticated Modal HTTPS endpoint for the
existing OpenMontage LTX provider. Local orchestration does not require Modal.

## Included

- Official LTX-2.3 distilled 1.1 pipeline, pinned to Lightricks/LTX-2 commit
  `d151147788a9284cca791edc6ce898007e727fe6`.
- A100-80GB GPU function.
- Persistent Modal Volume for downloaded model files.
- Bearer-token authentication and bounded request validation.
- MP4 returned as base64 JSON for the OpenMontage client.

Model weights are tens of gigabytes. Accept the LTX-2.3 Community License and
Google Gemma license, and verify Hugging Face access to
`Lightricks/LTX-2.3` and `google/gemma-3-12b-it` before deployment.

## 1. Create the Modal secret

In the Modal dashboard, create a secret named `openmontage-ltx2` with:

- `HF_TOKEN`: Hugging Face token with access to both model repositories.
- `OPENMONTAGE_API_TOKEN`: long random token for OpenMontage-to-Modal authentication.

Do not commit these values or put them in GitHub.

## 2. Install and authenticate the CLI

From the repository root:

```powershell
py -3.11 -m venv .venv-modal
.\.venv-modal\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r docker/modal_ltx2/requirements.txt
modal setup
```

On macOS/Linux, use `python3.11 -m venv .venv-modal` and activate
`.venv-modal/bin/activate`.

## 3. Deploy

```bash
modal deploy docker/modal_ltx2/app.py
```

Copy the HTTPS function URL printed by Modal.

## 4. Configure OpenMontage

Add these values to your local `.env`:

```dotenv
MODAL_LTX2_ENDPOINT_URL=https://YOUR-MODAL-ENDPOINT.modal.run
MODAL_LTX2_API_TOKEN=the-same-token-stored-in-the-Modal-secret
```

The default generation geometry is vertical 576x1024, 121 frames at 24 FPS.
The final compositor must conform the result to the delivery target: 9:16,
1080x1920, 30 FPS. Generated clips are source assets, not final deliverables.

## 5. Smoke test and cost control

Run one short generation through the normal OpenMontage provider route. The first
request downloads model weights and may take substantial time. Do not run load
tests or repeated generations before reviewing the first billable result.

The GPU function uses A100-80GB. The default `LTX_QUANTIZATION=fp8-cast` is
configurable as a Modal environment variable. The current implementation caches
model files in a Volume but starts a new CLI process for each request, so model
initialization still adds latency.

The upstream distilled pipeline has a fixed denoising schedule; generic `steps`
and `negative_prompt` request fields are not exposed by that pipeline. The
reference-image URL path accepts HTTPS URLs resolving to public IP addresses,
refuses redirects, and caps downloads at 20 MiB.

This deployment is not production-ready until a real authenticated GPU generation
has completed and its MP4 has been inspected.
