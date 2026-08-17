# Submitting to the Arch User Repository (AUR)

This directory contains a ready-to-submit Arch package:

- `PKGBUILD`
- `.SRCINFO` (generated with `makepkg --printsrcinfo`)
- `keydous-nj81-1.0.0.tar.gz` source tarball (from the v1.0.0 GitHub release)

## Local build check

```sh
cd packaging/aur
makepkg -si          # builds + installs the package
makepkg --printsrcinfo   # must match .SRCINFO exactly
namcap PKGBUILD      # optional: packaging lints
```

## Submit

1. Create an AUR account at <https://aur.archlinux.org> and add your SSH
   key in *Account → My Account → SSH Keys*.
2. Clone the AUR package repo:

   ```sh
   git clone ssh://aur@aur.archlinux.org/keydous-nj81.git
   ```

3. Copy `PKGBUILD` and `.SRCINFO` into the clone and push:

   ```sh
   cd keydous-nj81
   cp <this-dir>/PKGBUILD <this-dir>/.SRCINFO .
   git add PKGBUILD .SRCINFO
   git commit -m "keydous-nj81 1.0.0-1"
   git push origin master
   ```

4. Publish the git repo on the AUR site (or push an empty repo to register it).

Keep `pkgver`/`pkgrel` in sync with the GitHub release tag and update
`sha256sums`/`.SRCINFO` whenever the tarball changes.
