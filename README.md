# APT repository: keydous-nj81

Add the repo and install:

```sh
sudo install -Dm644 apt-repo.asc /etc/apt/keyrings/keydous-nj81.asc
echo "deb [signed-by=/etc/apt/keyrings/keydous-nj81.asc] <REPO_URL> stable main" \
  | sudo tee /etc/apt/sources.list.d/keydous-nj81.list
sudo apt update
sudo apt install keydous-nj81
```

Replace `<REPO_URL>` with the HTTPS URL that serves this directory
(see the project README for GitHub Pages instructions).

Signing key: `apt-repo.asc`
