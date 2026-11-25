"""
Liens préremplis d'agent-manager-savoye (0 token) : le manager ouvre l'agent au bon endroit, avec ce qu'il sait.

Paramètres d'adresse (contrat commun aux agents, agent-manager-savoye/manager/liens.py) :
    ?source=manager&page=<page>&ticket=<CLE>&projet=<client>&question=<texte>&contexte=<résumé>

- page : page de l'IHM (app.PAGES), déjà lue seule au rechargement (?page=…) ;
- ticket : clé Jira, posée dans « Lancement » comme si elle venait d'une recherche (rien n'est lancé) ;
- projet : client de l'onglet « Cucumber », s'il est connu ;
- question : question PRÉREMPLIE dans l'onglet « Assistant », envoyée seulement par un clic de l'utilisateur ;
- contexte : résumé du manager, affiché en tête de page.
Un lien n'est appliqué qu'une fois par session (signature) : les choix faits ensuite dans l'IHM sont gardés. Toute
valeur invalide est ignorée. Aucune action (Jira, Git, Jenkins, Claude) n'est déclenchée par un lien.

Construction (``parametres``, ``construire``) : partagée par agent-manager-savoye (manager/liens.py, qui y ajoute ses
onglets et ses redirections) et par les agents qui ouvrent un autre agent (ex. agent-retrospective → dev-tool avec
``page=developper&depot=…&demande=…``). Les paramètres complets sont alors
``page, ticket, projet, conversation, question, demande, depot, contexte`` ; ``demande`` et ``depot`` sont lus par
dev-tool, pas par ``lire``. Aucun secret ni donnée nominative dans un lien : il passe par l'historique du navigateur.
"""
import re
from urllib.parse import urlencode

TEXTE_MAX = 1500
CONTEXTE_MAX = 600
_TICKET = re.compile(r"[A-Z][A-Z0-9_]+-\d+")
_PROJET = re.compile(r"[\w .@-]{1,80}")
_CONVERSATION = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9]{6}")
PARAMETRES = ("page", "ticket", "projet", "conversation", "question", "demande", "depot", "contexte")


def _texte(valeur, limite: int) -> str:
    valeur = " ".join(str(valeur or "").split()) if limite == CONTEXTE_MAX else str(valeur or "").strip()
    return valeur[:limite]


def lire(params: dict, pages=()) -> dict:
    """Paramètres d'un lien du manager, validés ; {} si l'adresse ne vient pas du manager."""
    params = {k: (v[0] if isinstance(v, list) and v else v) for k, v in (params or {}).items()}
    if params.get("source") != "manager":
        return {}
    ticket = str(params.get("ticket") or "").strip().upper()
    projet = str(params.get("projet") or "").strip()
    page = str(params.get("page") or "").strip()
    lien = {"page": page if page in pages else "",
            "ticket": ticket if _TICKET.fullmatch(ticket) else "",
            "projet": projet if _PROJET.fullmatch(projet) else "",
            "question": _texte(params.get("question"), TEXTE_MAX),
            "contexte": _texte(params.get("contexte"), CONTEXTE_MAX)}
    return {k: v for k, v in lien.items() if v}


def signature(lien: dict) -> str:
    return "|".join(f"{k}={lien[k]}" for k in sorted(lien))


def projet_connu(projet: str, connus) -> str:
    """Client connu correspondant au projet du manager (casse et séparateurs ignorés) ; '' sinon."""
    cle = re.sub(r"[\s_.-]+", "", (projet or "").lower())
    return next((c for c in connus or [] if re.sub(r"[\s_.-]+", "", str(c).lower()) == cle), "") if cle else ""


def projet_jira(ticket: str) -> str:
    return ticket.rsplit("-", 1)[0] if ticket else ""


def _borne(valeur, limite: int) -> str:
    """Texte coupé à `limite` caractères, avec « … » s'il est tronqué."""
    valeur = str(valeur or "").strip()
    return valeur if len(valeur) <= limite else valeur[:limite - 1].rstrip() + "…"


def parametres(pages=(), page: str = "", ticket: str = "", projet: str = "", conversation: str = "",
               question: str = "", demande: str = "", depot: str = "", contexte: str = "") -> dict:
    """
    Paramètres validés d'un lien vers un agent dont les pages connues sont `pages` (valeurs vides ou invalides
    retirées ; {} s'il ne reste rien, sinon source=manager en tête).
    """
    ticket = str(ticket or "").strip().upper()
    valeurs = {
        "page": page if page and page in pages else "",
        "ticket": ticket if _TICKET.fullmatch(ticket) else "",
        "projet": str(projet or "").strip() if _PROJET.fullmatch(str(projet or "").strip()) else "",
        "conversation": str(conversation or "").strip()
        if _CONVERSATION.fullmatch(str(conversation or "").strip()) else "",
        "question": _borne(question, TEXTE_MAX),
        "demande": _borne(demande, TEXTE_MAX),
        "depot": str(depot or "").strip() if _PROJET.fullmatch(str(depot or "").strip()) else "",
        "contexte": _borne(contexte, CONTEXTE_MAX),
    }
    retenus = {k: v for k, v in valeurs.items() if v}
    return {"source": "manager", **retenus} if retenus else {}


def construire(url: str, pages=(), **valeurs) -> str:
    """Adresse de l'agent complétée des paramètres préremplis (l'adresse seule s'il n'y a rien à transmettre)."""
    params = parametres(pages, **valeurs)
    return f"{url.rstrip('/')}/?{urlencode(params)}" if params else url
