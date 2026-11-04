"""Gera o Pix "copia e cola" (BR Code estático, padrão do Banco Central) e o QR Code da página Apoie.

Uso (uma vez, quando a chave existir ou mudar):
    pip install "qrcode[pil]"
    python scripts/pix.py --chave "<chave>" --nome "Nome do recebedor" --cidade "Cidade"

Grava site/assets/pix.json (lido pela página apoie.html) e site/assets/img/pix-qr.png.
O valor fica em aberto: quem apoia escolhe no app do banco.
"""
import argparse, json, os, unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ascii(s, limite):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.split())[:limite]


def _campo(id_, valor):
    return f"{id_}{len(valor):02d}{valor}"


def crc16(dados):
    """CRC16-CCITT (polinômio 0x1021, valor inicial 0xFFFF), exigido no campo 63 do BR Code."""
    crc = 0xFFFF
    for b in dados.encode():
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def br_code(chave, nome, cidade, txid="***"):
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", chave.strip())
    corpo = (_campo("00", "01") + _campo("26", conta) + _campo("52", "0000") + _campo("53", "986")
             + _campo("58", "BR") + _campo("59", _ascii(nome, 25)) + _campo("60", _ascii(cidade, 15))
             + _campo("62", _campo("05", txid)) + "6304")
    return corpo + crc16(corpo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chave", required=True)
    ap.add_argument("--nome", required=True, help="nome do recebedor, como aparece no banco (até 25 letras)")
    ap.add_argument("--cidade", required=True, help="cidade do recebedor (até 15 letras)")
    a = ap.parse_args()
    codigo = br_code(a.chave, a.nome, a.cidade)
    import qrcode
    img = qrcode.make(codigo, box_size=12, border=2)
    img.save(os.path.join(RAIZ, "site", "assets", "img", "pix-qr.png"))
    with open(os.path.join(RAIZ, "site", "assets", "pix.json"), "w", encoding="utf-8") as f:
        json.dump({"chave": a.chave.strip(), "nome": a.nome.strip(), "cidade": a.cidade.strip(),
                   "copia_e_cola": codigo, "qr": "assets/img/pix-qr.png"}, f, ensure_ascii=False, indent=1)
    print("Pix gerado:", codigo)


if __name__ == "__main__":
    main()
