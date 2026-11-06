# SWORD‑le Pipeline

Tools for the generation of the SWORD Localy Expertised database for SWOT

**sword-le** is a geospatial processing pipeline designed to industrialize the selection, correction, and merging reaches coming from:

1. **SWORD** : SWORD Explorer(https://www.swordexplorer.com/)

2. **REPLACEMENT dataset** :  BD TOPAGE [https://www.data.gouv.fr/datasets/bd-topage-r](https://www.data.gouv.fr/datasets/bd-topage-r)
=> A manual pre‑selection step is required to choose the relevant TOPAGE reaches to use for each study area. These selected reaches will be used to correct or replace corresponding SWORD reaches inside and/or outside the mask.

3. **Obstruction dataset** : (https://figshare.com/articles/dataset/DL-GROD_csv/30041797?file=57619903) The obstruction dataset contains the locations of river obstructions 
.

## Installing / Getting started

The pipeline runs in a dedicated Conda environment defined
* Python **3.10**
* Main libraries: `geopandas`, `shapely`, `fiona`, `pyproj`, `geopy`, `matplotlib`, `tqdm`

```shell
git clone https://github.com/csgroup-oss/sword-le
cd sword_le/
conda create -n sword_le_env 
conda activate sword_le_env 
pip install . #need pyproject.toml
```

## Initial Configuration

* All input shapefiles **must be in EPSG:4326**
* Valid geometries (LineString / MultiLineString)

## Developing

```shell
git clone https://github.com/csgroup-oss/sword-le
cd sword_le/
```

## Features

The pipeline is executed from the command line.

```bash
python replace_reach_geometry.py \
    --path_sword /path/to/sword.gpkg \
    --path_replacement /path/to/replacement.gpkg \
    --path_output /path/to/output_directory \
    --replacement_id 1

python split_long_reaches.py \
    --path_sword /path/to/sword.gpkg \
    --path_output /path/to/output_directory \
    --max_length 30000 \
    --long_reach_id 1

python split_on_obstructions.py \
    --path_sword /path/to/sword.gpkg \
    --path_obstruction_csv /path/to/obstructions.csv \
    --path_output /path/to/output_directory \
    --obstruction_id 1

python generate_nodes.py \
    --path_sword /path/to/updated_sword.gpkg \
    --path_sword_nodes /path/to/sword_nodes.gpkg \
    --path_metadata /path/to/modification_metadata.json \
    --path_output /path/to/output_directory
```


### Outputs

The pipeline automatically generates gpkg.

### License

The data are sourced from the following databases:
 - SWOT River Database (SWORD) : https://www.swordexplorer.com/ 
License : Creative Commons 4.0 International License (CC by)

 - Topage database :  https://www.data.gouv.fr/datasets/bd-topage-r
License : Licence Ouverte / Open Licence version 2.0


## Links

- Repository: https://github.com/csgroup-oss/sword-le
- Issue tracker: https://github.com/csgroup-oss/sword-le/issues


## Copyright & Licensing

Copyright 2026, CS GROUP

This project is licensed under the Apache License 2.0. The full text of the license is available in the [LICENSE.txt](LICENSE.txt) file.
