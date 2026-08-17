#!/usr/bin/env bash
# Build a signed APT repository from the built .deb files.
#
# Output: ./apt-repo/  (a Debian repo you can serve over HTTPS, e.g.
# GitHub Pages). Also writes the signing public key to apt-repo.asc and a
# usage README.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$SRC/packaging/apt-repo"
DIST="stable"
COMP="main"
ARCH="amd64"

rm -rf "$OUT"
mkdir -p "$OUT/pool/$COMP/k/keydous-nj81" \
         "$OUT/dists/$DIST/$COMP/binary-$ARCH"

# --- signing key (one-time; reused across runs if present) ----------------
GNUPG="$OUT/gnupg"
mkdir -p "$GNUPG"
chmod 700 "$GNUPG"
KEYID=$(gpg --homedir "$GNUPG" --list-secret-keys --keyid-format=long 2>/dev/null \
          | awk '/^sec/{split($2,a,"/"); print a[2]; exit}')
if [ -z "$KEYID" ]; then
  gpg --homedir "$GNUPG" --batch --gen-key - <<EOF
%no-protection
Key-Type: eddsa
Key-Curve: ed25519
Key-Usage: sign
Name-Real: Keydous NJ81 Driver (APT)
Name-Email: yapplecunt@users.noreply.github.com
Expire-Date: 0
EOF
  KEYID=$(gpg --homedir "$GNUPG" --list-secret-keys --keyid-format=long 2>/dev/null \
            | awk '/^sec/{split($2,a,"/"); print a[2]; exit}')
fi
gpg --homedir "$GNUPG" --armor --export "$KEYID" > "$OUT/apt-repo.asc"

# --- pool ------------------------------------------------------------------
cp "$SRC"/keydous-nj81_*_all.deb "$OUT/pool/$COMP/k/keydous-nj81/"

# --- Packages ----------------------------------------------------------------
pushd "$OUT" >/dev/null
dpkg-scanpackages --arch all "pool/$COMP" 2>/dev/null \
  | sed "s|Pool:|pool:|" \
  > "dists/$DIST/$COMP/binary-$ARCH/Packages"
gzip -9n -c "dists/$DIST/$COMP/binary-$ARCH/Packages" \
  > "dists/$DIST/$COMP/binary-$ARCH/Packages.gz"
apt-ftparchive --md5 --sha1 --sha256 -o "APT::FTPArchive::Release::Origin=Keydous NJ81 Driver" \
  -o "APT::FTPArchive::Release::Label=keydous-nj81" \
  -o "APT::FTPArchive::Release::Suite=$DIST" \
  -o "APT::FTPArchive::Release::Codename=$DIST" \
  -o "APT::FTPArchive::Release::Components=$COMP" \
  -o "APT::FTPArchive::Release::Architectures=$ARCH" \
  release "dists/$DIST" > "dists/$DIST/Release"
popd >/dev/null

gpg --homedir "$GNUPG" --default-key "$KEYID" --detach-sign --armor \
  -o "$OUT/dists/$DIST/Release.gpg" "$OUT/dists/$DIST/Release"
gpg --homedir "$GNUPG" --default-key "$KEYID" --clearsign \
  -o "$OUT/dists/$DIST/InRelease" "$OUT/dists/$DIST/Release"

cat > "$OUT/README.md" <<EOF
# APT repository: keydous-nj81

Add the repo and install:

\`\`\`sh
sudo install -Dm644 apt-repo.asc /etc/apt/keyrings/keydous-nj81.asc
echo "deb [signed-by=/etc/apt/keyrings/keydous-nj81.asc] <REPO_URL> stable main" \\
  | sudo tee /etc/apt/sources.list.d/keydous-nj81.list
sudo apt update
sudo apt install keydous-nj81
\`\`\`

Replace \`<REPO_URL>\` with the HTTPS URL that serves this directory
(see the project README for GitHub Pages instructions).

Signing key: \`apt-repo.asc\`
EOF

echo "APT repo written to $OUT"
echo "signing key: $KEYID"
echo "serve this directory over HTTPS (e.g. GitHub Pages) and point"
echo "  deb [signed-by=...] <URL> stable main"
echo "at it."
