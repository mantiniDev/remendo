"""Mostra os campos reais devolvidos pela API (rode antes da primeira carga)."""
import json, sys
from .emendas import paginas

ano = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
primeira = next(paginas("/emendas", {"ano": ano}))
print("Campos de /emendas:", json.dumps(primeira, ensure_ascii=False, indent=1))
doc = next(paginas(f"/emendas/documentos/{primeira.get('codigoEmenda')}"), None)
print("Campos de /emendas/documentos:", json.dumps(doc, ensure_ascii=False, indent=1))
