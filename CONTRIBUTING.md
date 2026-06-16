# Contributing to Dakera

Thank you for your interest in contributing to Dakera! This document covers how to contribute code, report issues, and participate in the community.

## Getting Started

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run tests and linting
5. Commit your changes (`git commit -m 'Add your feature'`)
6. Push to your branch (`git push origin feature/your-feature`)
7. Open a Pull Request

## Development Setup

**Prerequisites:** Docker and Docker Compose

```bash
# Validate Docker Compose configuration
docker compose -f docker/docker-compose.yml config

# Test locally
docker compose up
```

## Code Style

- Follow the existing code style and conventions
- Write clear, descriptive commit messages
- Add tests for new functionality
- Update documentation as needed

## Pull Request Guidelines

- Keep PRs focused on a single change
- Include a clear description of what changed and why
- Ensure all CI checks pass
- Link relevant issues

## Reporting Issues

Use the [Bug Report](https://github.com/Dakera-AI/dakera-deploy/issues/new?template=bug_report.md) template to report bugs. Please include:
- Deployment method (Docker Compose, Helm, K8s)
- Steps to reproduce the issue
- Expected vs actual behavior

Have a feature idea? Use the [Feature Request](https://github.com/Dakera-AI/dakera-deploy/issues/new?template=feature_request.md) template.

## GitHub Discussions

[GitHub Discussions](https://github.com/Dakera-AI/dakera-deploy/discussions) is the best place for:

- **Sharing what you've built** — use the [Show and tell](https://github.com/Dakera-AI/dakera-deploy/discussions?discussions_q=category%3A%22Show+and+tell%22) category to share integrations, deployment patterns, or projects using Dakera
- **Asking questions** — use [Q&A](https://github.com/Dakera-AI/dakera-deploy/discussions/categories/q-a) for questions about configuration, deployment, or usage
- **Proposing ideas** — use [Ideas](https://github.com/Dakera-AI/dakera-deploy/discussions/categories/ideas) for feature suggestions before opening an issue

### Discussion etiquette

- Search existing discussions before opening a new one — your question may already be answered
- Use a clear, descriptive title that helps others find the thread later
- Include your Dakera version and deployment method (Docker Compose, Helm, Kubernetes) when relevant
- Keep discussions focused — if a conversation evolves into a concrete bug or feature request, open an issue and link back to the discussion
- Be respectful and constructive; we welcome contributors at all experience levels

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you agree to uphold these standards. Instances of unacceptable behavior may be reported to the maintainers via [GitHub Security Advisories](https://github.com/Dakera-AI/dakera-deploy/security/advisories/new) or by opening a private discussion with the team.

## Security Vulnerabilities

**Do not open public issues for security vulnerabilities.** See [SECURITY.md](SECURITY.md) for responsible disclosure instructions — report via [GitHub Security Advisories](https://github.com/dakera-ai/dakera-deploy/security/advisories/new).

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
