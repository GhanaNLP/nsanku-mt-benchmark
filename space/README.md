---
title: nsanku MT Benchmark
emoji: 📄
colorFrom: blue
colorTo: green
sdk: static
pinned: false
license: mit
tags:
  - machine-translation
  - ghana
  - benchmark
  - leaderboard
---

# nsanku MT Benchmark

Document-level machine translation benchmark for Ghanaian languages ↔ English, scored separately in each direction.

Systems translate whole documents (one paragraph per request) and are scored with **chrF2**
(sacreBLEU) against human translations. Results are recorded **per dataset** (currently the Ministry of
Finance's *Citizens' Budget*; more datasets will be added), and within a direction, a language's score is the
mean of its per-dataset scores. The two directions are never averaged together. The *Datasets* tab links to the source and the data in the repo.

- GitHub Repository: [GhanaNLP/nsanku-mt-benchmark](https://github.com/GhanaNLP/nsanku-mt-benchmark)
- Dataset notes: [docs/datasets.md](https://github.com/GhanaNLP/nsanku-mt-benchmark/blob/main/docs/datasets.md)
