# Security Policy

This project is not actively maintained and the authors make no claims about its security. See:
- [README.md](/README.md)
- [THREAT_MODEL.md](/threat-modeling/THREAT_MODEL.md)

## Updating dependencies

The system has the following entry points for dependencies:
- [Dockerfile](/Dockerfile)
- [devcontainer.json](/.devcontainer/devcontainer.json), covering both `extensions` and `features`
- [pyproject.toml](./pyproject.toml)

When submitting a PR to edit dependencies, you must also update the threat model with an
argument for why the dependency is reasonable to trust and why its benefits outweigh the risks.
See the dependency management sections in the [THREAT_MODEL.md](/threat-modeling/THREAT_MODEL.md)
for details.

## Reporting a vulnerability

Feel free to:

- Create a PR and fix it
- Contact us at hello@titaniumbirch.com
