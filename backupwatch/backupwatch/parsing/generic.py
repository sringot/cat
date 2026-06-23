"""Parser générique : déduit l'état d'une sauvegarde par analyse de mots-clés.

Conçu pour fonctionner « à l'aveugle », quel que soit le logiciel émetteur, en
attendant des parsers spécialisés. Il gère le français et l'anglais et évite les
faux positifs courants (« 0 erreur », « no errors », « Errors: 0 »…).
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..models import BackupResult, BackupStatus, RawEmail
from ..textutils import html_to_text
from .base import BackupParser

# Mots de négation qui annulent un terme d'état (« aucune erreur », « 0 warning »).
NEG_WORDS = {"0", "no", "zero", "zéro", "aucun", "aucune", "sans", "without", "non"}

# Termes d'état, du plus grave au moins grave (l'ordre compte pour le tri).
STATUS_TERMS = [
    (
        BackupStatus.FAILED,
        [
            "failed", "failure", "error", "errors", "échec", "echec", "erreur",
            "erreurs", "aborted", "abort", "unsuccessful", "fatal", "critical",
            # Formes verbales françaises (Synology, QNAP… : « la tâche a échoué »)
            "échoué", "échouée", "échoués", "échouées",
            "echoue", "echouee", "echoues", "echouees",
        ],
    ),
    (
        BackupStatus.WARNING,
        ["warning", "warnings", "avertissement", "attention", "skipped", "partially"],
    ),
    (
        BackupStatus.SUCCESS,
        [
            "success", "successful", "succeeded", "completed", "complete",
            "successfully", "succès", "succes", "réussi", "reussi", "terminé",
            "termine", "ok",
        ],
    ),
]

# Détection du logiciel source à partir du contenu.
SOURCE_HINTS = [
    ("Veeam", ["veeam"]),
    ("Acronis", ["acronis"]),
    ("Synology", ["synology", "hyper backup", "active backup", "quickconnect"]),
    ("QNAP", ["qnap", "hybrid backup"]),
    ("Proxmox", ["vzdump", "proxmox"]),
    ("Nakivo", ["nakivo"]),
    ("Datto", ["datto"]),
    ("Altaro / Hornetsecurity", ["altaro"]),
    ("Cohesity", ["cohesity"]),
    ("Windows Server Backup", ["windows server backup", "wbadmin"]),
    ("Veritas Backup Exec", ["backup exec", "veritas"]),
]

JOB_PATTERNS = [
    re.compile(r"job\s*['\"]([^'\"]+)['\"]", re.IGNORECASE),
    re.compile(r"t[âa]che\s*['\"]([^'\"]+)['\"]", re.IGNORECASE),
    re.compile(r"backup\s+job\s+([\w \-]+?)\s+(?:finished|completed|failed)", re.IGNORECASE),
    re.compile(r"backup of\s+([\w \-\.]+?)\s+(?:succeeded|completed|failed|finished)", re.IGNORECASE),
    re.compile(r"sauvegarde de\s+([^\-—:]+)", re.IGNORECASE),
]

SIZE_CTX_RE = re.compile(
    r"(?:size|taille|transferred|processed|data read|donn[ée]es|volume)[^\d]{0,20}"
    r"(\d+(?:[.,]\d+)?\s?(?:[KMGT]i?B|[KMGT]o|octets))",
    re.IGNORECASE,
)
SIZE_RE = re.compile(r"\b(\d+(?:[.,]\d+)?\s?(?:[KMGT]i?B|[KMGT]o))\b")
DURATION_RE = re.compile(
    r"(?:duration|dur[ée]e|elapsed|temps(?:\s+total)?)[^\d]{0,20}"
    r"(\d{1,2}:\d{2}:\d{2}|\d+\s?(?:h|min|minutes?|heures?))",
    re.IGNORECASE,
)


def _term_present(text: str, term: str) -> bool:
    """True si `term` apparaît dans `text` sans négation ni « : 0 »."""
    pattern = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)
    for match in pattern.finditer(text):
        before = text[max(0, match.start() - 16):match.start()].lower()
        after = text[match.end():match.end() + 8].lower()
        tokens = re.findall(r"[\wà-ÿ']+", before)
        if tokens and tokens[-1] in NEG_WORDS:
            continue
        if re.match(r"^[\s:=]*0(?!\d)", after):  # « Errors: 0 », « warnings 0 »
            continue
        return True
    return False


def _detect_status(subject: str, body: str) -> BackupStatus:
    for scope in (subject, body):
        for status, terms in STATUS_TERMS:
            if any(_term_present(scope, term) for term in terms):
                return status
    return BackupStatus.UNKNOWN


def _detect_source(text: str) -> Optional[str]:
    low = text.lower()
    for name, hints in SOURCE_HINTS:
        if any(hint in low for hint in hints):
            return name
    return None


def _extract_job(subject: str) -> Optional[str]:
    for pattern in JOB_PATTERNS:
        match = pattern.search(subject)
        if match:
            return match.group(1).strip(" .:-")
    return None


def _extract_client(email: RawEmail) -> str:
    # 1) Tag entre crochets en début de sujet, p. ex. « [ClientX] ... ».
    match = re.search(r"\[([^\]]+)\]", email.subject)
    if match:
        candidate = match.group(1).strip()
        if 1 < len(candidate) <= 40:
            return candidate
    # 2) Nom affiché de l'expéditeur (souvent le serveur/site client).
    name = (email.sender_name or "").strip()
    if name and name.lower() not in {"backup", "noreply", "no-reply", "administrator"}:
        return name
    # 3) Domaine de l'expéditeur.
    if "@" in (email.sender_address or ""):
        return email.sender_address.split("@", 1)[1]
    return email.sender_address or "Inconnu"


def _extract_size(body: str) -> Optional[str]:
    match = SIZE_CTX_RE.search(body) or SIZE_RE.search(body)
    return match.group(1).strip() if match else None


def _extract_duration(body: str) -> Optional[str]:
    match = DURATION_RE.search(body)
    return match.group(1).strip() if match else None


# Mots qui introduisent une cause d'échec/avertissement (lignes à privilégier).
REASON_WORDS = ["reason", "raison", "cause", "motif", "detail", "détail"]


def _extract_detail(body: str, status: BackupStatus) -> str:
    if status not in (BackupStatus.FAILED, BackupStatus.WARNING):
        return ""
    terms = next(t for s, t in STATUS_TERMS if s == status)
    triggers = terms + REASON_WORDS
    candidates = [
        line.strip()
        for line in body.splitlines()
        if line.strip() and any(_term_present(line, term) for term in triggers)
    ]
    if not candidates:
        return ""
    # On privilégie la ligne la plus longue : c'est en général celle qui décrit
    # la cause (« Error: ... », « Reason: ... ») plutôt qu'un simple « Failed ».
    return max(candidates, key=len)[:200]


class GenericParser(BackupParser):
    name = "generic"

    def can_parse(self, email: RawEmail) -> bool:  # toujours applicable (repli)
        return True

    def parse(self, email: RawEmail) -> List[BackupResult]:
        body = email.body_text or html_to_text(email.body_html)
        combined = f"{email.subject}\n{body}"

        status = _detect_status(email.subject, body)
        return [
            BackupResult(
                client=_extract_client(email),
                status=status,
                received=email.received,
                job=_extract_job(email.subject),
                source_tool=_detect_source(combined),
                size=_extract_size(body),
                duration=_extract_duration(body),
                detail=_extract_detail(body, status),
                subject=email.subject,
                email_id=email.id,
            )
        ]
