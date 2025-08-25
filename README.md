# Simuladores Interactivos de Blockchain y Minería Bitcoin

Este proyecto contiene dos simuladores didácticos para terminal que permiten experimentar y visualizar conceptos clave de la tecnología blockchain y la minería de Bitcoin.

---

## Simulador de Minería Bitcoin

Permite experimentar el proceso de prueba y error para encontrar nonces que produzcan hashes válidos según la dificultad elegida, utilizando cabeceras reales de bloques de Bitcoin.

### Características

- **Prueba de trabajo real:** Calcula el doble SHA-256 sobre el header de 80 bytes, como en Bitcoin.
- **Cabeceras reales:** Utiliza bloques extraídos de la red Bitcoin, almacenados en `blocks.json`.
- **Interfaz interactiva:** Ingresa nonces manualmente y observa los resultados en tiempo real.
- **Corte automático por tiempo:** El juego finaliza tras el tiempo configurado.
- **Beep multiplataforma:** Sonido al encontrar un hash válido.
- **Validación de nonces:** Advierte si repites un nonce que ya produjo un hash válido.

### Uso

```bash
python mineria_bitcoin_interactiva.py --blocks blocks.json --segundos 60 --dificultad 2 --verbose
```

Parámetros disponibles:

- `--blocks`: Ruta al archivo de bloques (por defecto `blocks.json`).
- `--segundos`: Tiempo de juego en segundos (por defecto 60).
- `--dificultad`: Cantidad de ceros iniciales requeridos en el hash (por defecto 1).
- `--verbose`: Muestra el hash de cada intento.

### Generar bloques

Para actualizar o crear tu propio `blocks.json`:

```bash
python make_blocks_json.py
```

O especifica alturas personalizadas:

```bash
python make_blocks_json.py 0 1 2 210000 700000
```

---

## Simulador de Integridad Blockchain

Demuestra visualmente cómo los bloques están encadenados por hash y cómo una alteración en cualquier bloque rompe la cadena, obligando a recalcular los nonces para restaurar la integridad.

### Características

- **Visualización de cadena:** Muestra cada bloque en una caja con colores y estado (OK/ROTO).
- **Alteración interactiva:** Permite modificar el contenido de cualquier bloque (excepto el último) y observar el efecto en la cadena.
- **Propagación de corrección:** Tras corregir el nonce de un bloque alterado, la reparación se propaga hacia adelante, bloque por bloque.
- **Ventana cronometrada:** Tienes un tiempo limitado para corregir cada bloque.
- **Hash real:** SHA-256 doble sobre los campos del bloque.
- **Dificultad configurable:** Número de ceros requeridos al inicio del hash.

### Uso

```bash
python blockchain_integridad_interactiva.py --bloques 6 --dificultad 2 --tiempo-fix 30
```

Parámetros disponibles:

- `--bloques`: Cantidad de bloques iniciales (por defecto 5).
- `--dificultad`: Ceros iniciales requeridos en el hash (por defecto 2).
- `--tiempo-fix`: Segundos para corregir nonces tras alteración/propagación (por defecto 30).

---

## Archivos principales

- `mineria_bitcoin_interactiva.py`: Simulador interactivo de minería Bitcoin.
- `blockchain_integridad_interactiva.py`: Simulador visual de integridad y propagación en blockchain.
- `make_blocks_json.py`: Script para generar/actualizar `blocks.json` usando la API pública de Blockchain.com.

---

## Requisitos

- Python 3.8 o superior.
- `pip` instalado para la gestión de dependencias.

## Instalación

1. Clonar el repositorio:
   ```bash
   git clone https://github.com/hipoloco/blockchain-simulator
   cd blockchain-simulator
   ```

2. Instalar las dependencias:
   - En Linux/MacOS:
     ```bash
     bash ./install_dependencies.sh
     ```
   - En Windows:
     ```cmd
     install_dependencies.bat
     ```

---

## Créditos y fuentes

- Cabeceras obtenidas de [Blockchain.com](https://www.blockchain.com/explorer/blocks/btc).
- Inspirado en el mecanismo de minería de Bitcoin.

## Colaboradores

- **hipoloco**: [https://github.com/hipoloco](https://github.com/hipoloco)
- **Kabuta14**: [https://github.com/Kabua14](https://github.com/Kabua14)
- **CasTeo7**: [https://github.com/CasTeo7](https://github.com/CasTeo7)

## Contribuciones

Las contribuciones son bienvenidas. Por favor, sigue estos pasos para colaborar:

1. Haz un fork del repositorio.
2. Crea una rama para tu funcionalidad o corrección (`git checkout -b feature/nueva-funcionalidad`).
3. Realiza tus cambios y haz commits claros y descriptivos.
4. Envía un pull request.

## Licencia

Este proyecto está bajo la Licencia MIT.
