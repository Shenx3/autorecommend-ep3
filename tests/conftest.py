import os
import pathlib
import sys
import tempfile

import pandas as pd

# Entorno de prueba: catalogo falso y variables de entorno antes de importar la API
TMP = tempfile.mkdtemp()
pd.DataFrame({
    "product_id": list(range(1001, 1016)),
    "price": [100.0 + i for i in range(15)],
    "brand": ["samsung", "apple", "xiaomi"] * 5,
    "category": ["electronics.smartphone"] * 15,
    "n_views": list(range(150, 0, -10)),
}).to_csv(os.path.join(TMP, "catalog.csv"), index=False)

os.environ.update(API_KEY="test-key", ARTIFACTS_DIR=TMP, DATA_DIR=TMP, RATE_LIMIT="1000/minute")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "api"))
