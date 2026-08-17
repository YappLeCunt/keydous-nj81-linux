# APT repository: keydous-nj81

This directory is served at
**https://yapplecunt.github.io/keydous-nj81-linux/** (GitHub Pages).

Add the repo and install:

```sh
sudo install -Dm644 apt-repo.asc /etc/apt/keyrings/keydous-nj81.asc
echo "deb [signed-by=/etc/apt/keyrings/keydous-nj81.asc] https://yapplecunt.github.io/keydous-nj81-linux/ stable main" \
  | sudo tee /etc/apt/sources.list.d/keydous-nj81.list
sudo apt update
sudo apt install keydous-nj81
```

Or install the `.deb` directly from a GitHub release:

```sh
wget https://github.com/YappLeCunt/keydous-nj81-linux/releases/latest/download/keydous-nj81_1.0.0_all.deb
sudo apt install ./keydous-nj81_1.0.0_all.deb
```

Signing key: `apt-repo.asc`
