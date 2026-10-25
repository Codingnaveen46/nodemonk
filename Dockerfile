# nodemonk — zero-install usage via Docker
# Build:  docker build -t nodemonk https://github.com/Codingnaveen46/nodemonk.git
# Run:    docker run --rm -v "$(pwd):/workspace" nodemonk build /workspace
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY nodemonk ./nodemonk
RUN pip install --no-cache-dir .

# Graphs are written next to the scanned corpus
WORKDIR /workspace
ENTRYPOINT ["nodemonk"]
CMD ["--help"]
