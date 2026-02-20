# clean-grocery-bot

[![Release](https://img.shields.io/github/v/release/stevin-wilson/clean-grocery-bot)](https://img.shields.io/github/v/release/stevin-wilson/clean-grocery-bot)
[![Build status](https://img.shields.io/github/actions/workflow/status/stevin-wilson/clean-grocery-bot/main.yml?branch=main)](https://github.com/stevin-wilson/clean-grocery-bot/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/stevin-wilson/clean-grocery-bot/branch/main/graph/badge.svg)](https://codecov.io/gh/stevin-wilson/clean-grocery-bot)
[![Commit activity](https://img.shields.io/github/commit-activity/m/stevin-wilson/clean-grocery-bot)](https://img.shields.io/github/commit-activity/m/stevin-wilson/clean-grocery-bot)
[![License](https://img.shields.io/github/license/stevin-wilson/clean-grocery-bot)](https://img.shields.io/github/license/stevin-wilson/clean-grocery-bot)

A serverless Telegram chatbot that helps you make cleaner food choices while grocery shopping. Search by product category and get AI-powered recommendations ranked by ingredient cleanliness — avoiding seed oils, artificial additives, and ultra-processed foods — based on your own configurable dietary preferences.

- **Github repository**: <https://github.com/stevin-wilson/clean-grocery-bot/>
- **Documentation** <https://stevin-wilson.github.io/clean-grocery-bot/>

## Getting started with your project

First, create a repository on GitHub with the same name as this project, and then run the following commands:

```bash
git init -b main
git add .
git commit -m "init commit"
git remote add origin git@github.com:stevin-wilson/clean-grocery-bot.git
git push -u origin main
```

Finally, install the environment and the pre-commit hooks with

```bash
make install
```

You are now ready to start development on your project!
The CI/CD pipeline will be triggered when you open a pull request, merge to main, or when you create a new release.

To finalize the set-up for publishing to PyPI or Artifactory, see [here](https://fpgmaas.github.io/cookiecutter-poetry/features/publishing/#set-up-for-pypi).
For activating the automatic documentation with MkDocs, see [here](https://fpgmaas.github.io/cookiecutter-poetry/features/mkdocs/#enabling-the-documentation-on-github).
To enable the code coverage reports, see [here](https://fpgmaas.github.io/cookiecutter-poetry/features/codecov/).

---

Repository initiated with [fpgmaas/cookiecutter-poetry](https://github.com/fpgmaas/cookiecutter-poetry).
