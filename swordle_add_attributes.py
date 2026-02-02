#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ajout de reach_len, x, y aux features corrigés de la SWORD.

Auteur : Abderrahmane AICHE (CS GROUP)
Date   : 05/02/2026


Version : Python  3.13

Description : 
    Ce script lit un shapefile d'entrée (la sortie du pipeline : swordle_prod_upgrade.py), 
    identifie les features dont toutes les propriétés sont None, 
    calcule la longueur du reach (reach_len) en mètres pour ces features, 
    puis ajoute les coordonnées x et y du point milieu du reach. 
    Enfin, il écrit un nouveau shapefile de sortie avec les modifications.
    
    Sortie générée (shapefiles) :

    - Un shapefile de sortie avec les features mises à jour (reach_len, x, y) pour les reaches corrigés de la SWORD.
"""

import argparse
import fiona
from shapely.geometry import LineString
import swordle


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ajout de reach_len, x, y aux features corrigés de la SWORD."
    )
    parser.add_argument("--file", required=True, help="Shapefile d'entrée")
    parser.add_argument("--outputfile", required=True, help="Shapefile de sortie")
    return parser.parse_args()


def main():
    args = parse_args()
    input_file = args.file
    output_file = args.outputfile

    # Étape 1 — Sélectionner les features dont TOUTES les propriétés sont None
    features_none = []
    with fiona.open(input_file, "r") as src:
        for feat in src:
            props = feat["properties"]
            if all(v is None for v in props.values()):
                features_none.append(feat)

    print(f"{len(features_none)} reaches avec toutes les propriétés à None")
    

    # Étape 2 — Ajouter reach_len
    updated_features = []
    for feat in features_none:
        # Calcul via swordle 
        reach_len = swordle.compute_reach_length(feat) # en mètres
        props = dict(feat.properties)
        props["reach_len"] = reach_len

        # Conserver la géométrie telle quelle
        new_feat = fiona.Feature(
            id=feat.id,
            geometry=feat.geometry,
            properties=props
        )
        updated_features.append(new_feat)
       

    # Étape 3 — Ajouter x et y à partir du point milieu (reach_len / 2)
    updated_features1 = []
    for feat in updated_features:
        geom = feat.geometry
        # Reconstruire le LineString depuis coords :
        coords = geom["coordinates"]
        line = LineString(coords)

        reach_len = feat.properties.get("reach_len")
        if reach_len is None:
            # Si reach_len n'a pas pu être calculé
            continue

        mid_point = line.interpolate(reach_len / 2.0)

        props = dict(feat.properties)
        props["x"] = float(mid_point.x)
        props["y"] = float(mid_point.y)

        updated_features1.append(
            fiona.Feature(
                id=feat.id,
                geometry=geom,
                properties=props
            )
        )

    # Index par id 
    updated_by_id = {f.id: f for f in updated_features1}

    # Étape 4 — Écriture : 
    with fiona.open(input_file, "r") as src:
        schema = src.schema.copy()
        crs = src.crs
        driver = src.driver

        with fiona.open(
            output_file,
            "w",
            driver=driver,
            crs=crs,
            schema=schema
        ) as dst:
            for feature in src:
                # Si la feature a été mise à jour, on écrit la version modifiée
                if feature.id in updated_by_id:
                    dst.write(updated_by_id[feature.id])
                else:
                    # Sinon, on recopie à l'identique
                    dst.write(feature)
    print(f"Fichier mis à jour avec les nouvelles propriétés des reaches corrigés : {output_file}")


if __name__ == "__main__":
    main()