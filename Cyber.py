# Cyber.py

import requests
import base64
import struct

def parse_relic_data_from_api(api_key: str) -> str:
    """
    Fetches binary relic data from the Alceaframe API, parses it,
    and returns a newline-delimited string of relic info.
    """
    url = f"https://api.alecaframe.example/relics?api_key={api_key}"
    response = requests.get(url)
    response.raise_for_status()
    binary_data = response.content

    relics = []
    offset = 0
    num_relics = struct.unpack_from('<I', binary_data, offset)[0]
    offset += 4

    for i in range(num_relics):
        if len(binary_data) < offset + 8:
            break  # incomplete record
        relic_type = binary_data[offset]
        refinement = binary_data[offset + 1]
        name = binary_data[offset + 2:offset + 6].decode('ascii', errors='ignore').strip('\x00')
        quantity = struct.unpack_from('<H', binary_data, offset + 6)[0]
        offset += 8
        relics.append(f"{name} | Type: {relic_type} | Refinement: {refinement} | Qty: {quantity}")

    return "\n".join(relics)
