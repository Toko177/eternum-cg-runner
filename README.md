# Eternum CG runner (public code only)

This is a public GitHub Actions runner for processing the `cgv1` release stored in the **private** repository `Toko177/eternum-cg-analysis`.

**Do not upload any CGs, archives, or contact sheets to this public repository.** All nine split-7z archive parts remain in the private repository.

## One-time setup

1. Create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new).
   - **Resource owner:** Toko177
   - **Repository access:** Only select repositories → `eternum-cg-analysis`
   - **Repository permissions → Contents:** Read and write
   - Choose a short expiration date. Metadata read permission is automatic.
2. Open the [runner repository's Actions secrets](https://github.com/Toko177/eternum-cg-runner/settings/secrets/actions).
3. Select **New repository secret** and set:
   - Name: `PRIVATE_REPO_TOKEN`
   - Secret: paste the token from step 1.
4. Open [Process private CG archive](https://github.com/Toko177/eternum-cg-runner/actions/workflows/process-private-cgs.yml). Select **Run workflow** on the `main` branch.

## What happens

- The public Actions runner uses the secret to privately download all nine parts of release `cgv1`.
- It extracts the images, inventories them, removes exact duplicates, and makes contact sheets.
- It commits the contact sheets and `image_index.csv` to `Toko177/eternum-cg-analysis` under `generated/cgv1/`.
- It first checks that the destination repository is still private.
- It uploads **no public Actions artifacts** and does not commit any images to this public repository.

## Security and limitations

Actions run logs are public. Do not print tokens or private image contents into logs. GitHub normally masks the secret, but avoid changing the workflow to enable verbose tracing.

A public runner does process the private material transiently inside GitHub Actions, so only run workflow code you trust. The generated contact sheets also contain source-image thumbnails; they remain in the private repository.

Image archives may exceed the free runner's disk space or allowed runtime. Processing has not yet been tested on the complete archive.

After a successful run, revoke the short-lived token in GitHub settings and delete `PRIVATE_REPO_TOKEN` from the public repository's Actions secrets.
