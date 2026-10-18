"""Liga o HTTPS das telas de demo no celular (porta 8443 -> API na 8000). Detalhes em src/triagem/https_celular.py.

Uso (com a API rodando):  python scripts/https_celular.py      — ou  scripts\\iniciar.ps1 -Celular, que já liga
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from triagem.https_celular import main  # noqa: E402

if __name__ == "__main__":
    main()
