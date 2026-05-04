"""Lightweight keyword-based tech skill extractor for job descriptions."""

from __future__ import annotations

import re

# Patterns checked in order; first match for a label wins (deduplication by label).
# Format: (regex_pattern, display_label)
_SKILL_PATTERNS: list[tuple[str, str]] = [
    # ── Languages ────────────────────────────────────────────────────────────
    (r"\bpython\b", "Python"),
    (r"\btypescript\b", "TypeScript"),
    (r"\bjavascript\b", "JavaScript"),
    (r"\bjava\b", "Java"),
    (r"\bgolang\b|\bgo\s+(?:lang|programming)\b", "Go"),
    (r"\brust\b", "Rust"),
    (r"\bc\+\+\b|\bcpp\b", "C++"),
    (r"\bc#\b|\.net\b|\bdotnet\b", "C#/.NET"),
    (r"\bruby\b", "Ruby"),
    (r"\bphp\b", "PHP"),
    (r"\bswift\b", "Swift"),
    (r"\bkotlin\b", "Kotlin"),
    (r"\bscala\b", "Scala"),
    (r"\bshell\b|\bbash\b", "Bash/Shell"),
    # ── Frontend ─────────────────────────────────────────────────────────────
    (r"\breact(?:\.js)?\b", "React"),
    (r"\bvue(?:\.js)?\b", "Vue.js"),
    (r"\bangular\b", "Angular"),
    (r"\bnext\.?js\b|\bnextjs\b", "Next.js"),
    (r"\bsvelte\b", "Svelte"),
    (r"\bhtml\b", "HTML"),
    (r"\bcss\b|\bsass\b|\bscss\b", "CSS/Sass"),
    (r"\btailwind\b", "Tailwind CSS"),
    # ── Backend / Frameworks ─────────────────────────────────────────────────
    (r"\bnode(?:\.js)?\b", "Node.js"),
    (r"\bdjango\b", "Django"),
    (r"\bflask\b", "Flask"),
    (r"\bfastapi\b", "FastAPI"),
    (r"\bspring(?:\s+boot)?\b", "Spring Boot"),
    (r"\bruby\s+on\s+rails\b|\brails\b", "Ruby on Rails"),
    (r"\bexpress(?:\.js)?\b", "Express.js"),
    (r"\blaravel\b", "Laravel"),
    # ── Databases ────────────────────────────────────────────────────────────
    (r"\bpostgresql\b|\bpostgres\b", "PostgreSQL"),
    (r"\bmysql\b", "MySQL"),
    (r"\bmongodb\b|\bmongo\b", "MongoDB"),
    (r"\bredis\b", "Redis"),
    (r"\belasticsearch\b", "Elasticsearch"),
    (r"\bsqlite\b", "SQLite"),
    (r"\bsql\b", "SQL"),
    (r"\bdynamodb\b", "DynamoDB"),
    (r"\bbigquery\b", "BigQuery"),
    (r"\bsnowflake\b", "Snowflake"),
    # ── Cloud / DevOps ────────────────────────────────────────────────────────
    (r"\baws\b|amazon\s+web\s+services\b", "AWS"),
    (r"\bazure\b", "Azure"),
    (r"\bgcp\b|google\s+cloud\b", "GCP"),
    (r"\bdocker\b", "Docker"),
    (r"\bkubernetes\b|\bk8s\b", "Kubernetes"),
    (r"\bterraform\b", "Terraform"),
    (r"\bci/cd\b|\bcicd\b|continuous\s+integration\b", "CI/CD"),
    (r"\bgit(?:hub|lab)?\b", "Git"),
    (r"\blinux\b", "Linux"),
    (r"\bjenkins\b", "Jenkins"),
    (r"\bansible\b", "Ansible"),
    # ── APIs / Architecture ───────────────────────────────────────────────────
    (r"\brest(?:ful)?(?:\s+api)?\b", "REST API"),
    (r"\bgraphql\b", "GraphQL"),
    (r"\bgrpc\b", "gRPC"),
    (r"\bmicroservices\b", "Microservices"),
    # ── ML / AI / Data ────────────────────────────────────────────────────────
    (r"\bmachine\s+learning\b", "Machine Learning"),
    (r"\bdeep\s+learning\b", "Deep Learning"),
    (r"\btensorflow\b", "TensorFlow"),
    (r"\bpytorch\b", "PyTorch"),
    (r"\bscikit.?learn\b", "Scikit-learn"),
    (r"\bllm\b|large\s+language\s+model\b", "LLM"),
    (r"\bopenai\b", "OpenAI"),
    (r"\blangchain\b", "LangChain"),
    (r"\bhugging.?face\b|\btransformers\b(?!\s+js)", "HuggingFace"),
    (r"\bpandas\b", "Pandas"),
    (r"\bnumpy\b", "NumPy"),
    (r"\bpyspark\b|\bapache\s+spark\b", "Apache Spark"),
    (r"\bairflow\b", "Airflow"),
    (r"\bdbt\b", "dbt"),
    (r"\bkafka\b", "Kafka"),
    (r"\bdatabricks\b", "Databricks"),
    # ── General SWE ───────────────────────────────────────────────────────────
    (r"\bagile\b|\bscrum\b", "Agile/Scrum"),
]

_COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pat, re.IGNORECASE), label)
    for pat, label in _SKILL_PATTERNS
]


def extract_skills(text: str, max_skills: int = 10) -> str:
    """Return a comma-separated list of tech skills found in *text*.

    Scans *text* against a curated set of tech-skill regex patterns and
    returns up to *max_skills* matched labels in the order they are first
    encountered in the pattern list.
    """
    if not text:
        return ""
    found: list[str] = []
    seen: set[str] = set()
    for pattern, label in _COMPILED:
        if label not in seen and pattern.search(text):
            found.append(label)
            seen.add(label)
        if len(found) >= max_skills:
            break
    return ", ".join(found)
