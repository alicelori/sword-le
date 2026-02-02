
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auteur : Abderrahmane AICHE (CS GROUP)
Date : 23/01/2026
''Adjusting script for new logic functions : find_upstream_downstream_reaches_using_mask''
Update Date : 04/02/2026

Version : Python  3.13

Description :
Pipeline de production SWORDLE (sélection, correction de la SWORD et export de shapefiles).
Sorties générées (shapefiles) :
 - test_rep_masked_out.shp
 - test_rep_masked_in.shp
 - test_src_masked_out.shp
 - test_points.shp
 - test_src_up_reach.shp
 - test_src_dw_reach.shp
 - test_rep_keeped.shp
 - test_src_keeped.shp
 - test_new_up_reach.shp
 - test_new_dw_reach.shp
 - test_complete.shp
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

import fiona
from shapely.geometry import mapping, shape
import swordle


# ==============================================================================================================
# Fonctions utilitaires pour la sauvegarde des ESRI shape file
# ==============================================================================================================

def ensure_dir(path: str):
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def load_first_geometry(shp_path: str):
    """Charge la première géométrie d'un shapefile (ex: masque polygonal)."""
    with fiona.open(shp_path, "r") as src:
        for feat in src:
            return shape(feat["geometry"])
    raise ValueError(f"Aucune géométrie trouvée dans {shp_path}")


def read_default_attributes(json_path: str) -> dict:
    with open(json_path, "r") as fin:
        return json.load(fin)


def _extract_geom_and_props(feature):
    """
    Retourne (geometry_mapping, properties) à partir d’entrées hétérogènes :
      - dict Fiona (Feature ou geometry)
      - objet avec __geo_interface__ (Feature ou geometry)
      - géométrie Shapely
    """
    # Dict Fiona
    if isinstance(feature, dict):
        if feature.get("type") == "Feature" and "geometry" in feature:
            geom_mapping = feature["geometry"]
            props = feature.get("properties", {})
        elif "geometry" in feature:
            geom_mapping = feature["geometry"]
            props = feature.get("properties", {})
        else:
            # Mapping de géométrie direct
            geom_mapping = feature
            props = {}
        return mapping(shape(geom_mapping)), props

    # Objet GeoPython avec __geo_interface__
    if hasattr(feature, "__geo_interface__"):
        gi = feature.__geo_interface__
        if gi.get("type") == "Feature":
            geom_mapping = gi["geometry"]
            props = gi.get("properties", {})
        else:
            geom_mapping = gi
            props = getattr(feature, "properties", {})
        return mapping(shape(geom_mapping)), props

    # Géométrie Shapely pure
    try:
        return mapping(feature), getattr(feature, "properties", {})
    except Exception as exc:
        raise TypeError(
            f"Type de feature non supporté pour l'écriture Fiona: {type(feature)}"
        ) from exc


def adapt_feature(feature, schema, default_attributes):
    """
    Adapte une 'feature' au schéma/crs de sortie :
      - géométrie normalisée (mapping GeoJSON)
      - propriétés limitées aux clés du schéma, complétées avec les valeurs par défaut
    """
    geom, props_src = _extract_geom_and_props(feature)
    props_out = {
        key: props_src.get(key, default_attributes.get(key, None))
        for key in schema["properties"].keys()
    }
    return {"geometry": geom, "properties": props_out}


def _geom_equals(a, b, tol: float = 0.0) -> bool:
    """
    Compare l'égalité géométrique entre deux features non identiques.
    - tol: tolérance pour equals_exact (0.0 par défaut), fallback sur equals topologique.
    """
    try:
        ga, _ = _extract_geom_and_props(a)
        gb, _ = _extract_geom_and_props(b)
        sa = shape(ga)
        sb = shape(gb)
        return sa.equals_exact(sb, tol) or sa.equals(sb)
    except Exception:
        return False


def write_features(path, features, schema, crs, default_attributes):
    """Écrit une liste de features en shapefile selon un schema/crs donnés."""
    ensure_dir(os.path.dirname(path))
    with fiona.open(path, "w", driver="ESRI Shapefile", crs=crs, schema=schema) as fout:
        for feature in features:
            fout.write(adapt_feature(feature, schema, default_attributes))


# ==============================================================================================================
# Pipeline principal
# ==============================================================================================================

def run_pipeline(mask_path: str,
                 sword_path: str,
                 logic: str,
                 replacement_path: str,
                 default_attr_path: str,
                 results_dir: str):
    logger = logging.getLogger("swordle_prod")

    # Préparation
    ensure_dir(results_dir)
    logger.info("Dossier résultats: %s", results_dir)

    # Chargement des entrées
    logger.info("Chargement du masque: %s", mask_path)
    mask = load_first_geometry(mask_path)

    logger.info("Chargement source (SWORD reaches): %s", sword_path)
    src = fiona.open(sword_path, "r")

    logger.info("Chargement replacement (TOPAGE): %s", replacement_path)
    rep = fiona.open(replacement_path, "r")
    logger.info("Éléments replacement: %d", len(rep))

    logger.info("Chargement des attributs par défaut: %s", default_attr_path)
    default_attributes = read_default_attributes(default_attr_path)

    # ==========================================================================================================
    # 1 - Sélections via masque
    # ==========================================================================================================
    logger.info("Sélection des reaches hors masque sur la source (SWORD)")
    src_masked_out = swordle.select_reaches_using_mask(src, mask, where="out")

    logger.info("Sélections in/out sur la couche de remplacement (TOPAGE)")
    rep_masked_in  = swordle.select_reaches_using_mask(rep, mask, where="in",  crs=rep.crs)
    rep_masked_out = swordle.select_reaches_using_mask(rep, mask, where="out", crs=rep.crs)

    logger.info("Application des attributs par défaut sur replacement (in/out)")
    rep_masked_in  = swordle.apply_default_attributes(rep_masked_in, default_attributes)
    rep_masked_out = swordle.apply_default_attributes(rep_masked_out, default_attributes)

    # ==========================================================================================================
    # 2 - Ajustements aux bords du masque
    # ==========================================================================================================
    logger.info("Recherche des reaches amont/aval à corriger")
    if logic == "1":
        logic_func = swordle.find_upstream_downstream_reaches_using_mask_logic1
    
    else:
        logic_func = swordle.find_upstream_downstream_reaches_using_mask_logic2
    
    logger.info(f"Utilisation de la logique {logic} pour la sélection amont/aval.")
    
    src_upstream_reach, src_downstream_reach = logic_func(src_masked_out, mask)   

    logger.info("Recherche des points d'intersection proches du masque")
    upstream_intersection_point = swordle.find_closest_intersection_point_to_the_mask(
        rep_masked_out, src_upstream_reach, mask
    )
    downstream_intersection_point = swordle.find_closest_intersection_point_to_the_mask(
        rep_masked_out, src_downstream_reach, mask
    )

    logger.info("Correction des reaches amont/aval avec les points d'intersection")
    upstream_reach = swordle.correct_reach_using_intersection_point(
        rep=rep_masked_out,
        src_reach=src_upstream_reach,
        intersection_point=upstream_intersection_point,
        mask=mask
    )
    downstream_reach = swordle.correct_reach_using_intersection_point(
        rep=rep_masked_out,
        src_reach=src_downstream_reach,
        intersection_point=downstream_intersection_point,
        mask=mask
    )

    # ==========================================================================================================
    # 3 - Ajustement des positions de reaches de replacement à l'intérieur du masque (confluences)
    # ==========================================================================================================
    logger.info("Ajustement des reaches replacement à l’intérieur du masque (confluences)")
    rectified_rep_features, upstream_reach, downstream_reach = swordle.adjust_reaches_with_confluence_using_mask(
        rep_masked_in, upstream_reach, downstream_reach, mask
    )

    # Attributs par défaut sur les objets finaux
    rectified_rep_features = swordle.apply_default_attributes(rectified_rep_features, default_attributes)
    upstream_reach['properties'] = default_attributes
    downstream_reach['properties'] = default_attributes

    # ==========================================================================================================
    # 4 - Sauvegardes
    # ==========================================================================================================
    logger.info("Écriture des sorties shapefile")

    # On utilise le schema / crs de la source comme base pour uniformiser
    src_schema = src.schema
    src_crs = src.crs

    # Fichiers de sélection
    write_features(os.path.join(results_dir, "test_rep_masked_out.shp"), rep_masked_out, src_schema, src_crs, default_attributes)
    write_features(os.path.join(results_dir, "test_rep_masked_in.shp"),  rep_masked_in,  src_schema, src_crs, default_attributes)
    write_features(os.path.join(results_dir, "test_src_masked_out.shp"), src_masked_out, src_schema, src_crs, default_attributes)

    # Points d'intersection
    points_schema = {'geometry': 'Point', 'properties': {}}
    with fiona.open(os.path.join(results_dir, "test_points.shp"), "w",
                    driver="ESRI Shapefile", crs=src_crs, schema=points_schema) as fout:
        fout.write({'geometry': mapping(upstream_intersection_point), 'properties': {}})
        fout.write({'geometry': mapping(downstream_intersection_point), 'properties': {}})

    # Reaches individuels 
    write_features(os.path.join(results_dir, "test_src_up_reach.shp"), [src_upstream_reach], src_schema, src_crs, default_attributes)
    write_features(os.path.join(results_dir, "test_src_dw_reach.shp"), [src_downstream_reach], src_schema, src_crs, default_attributes)
    write_features(os.path.join(results_dir, "test_rep_keeped.shp"),   rectified_rep_features, src_schema, src_crs, default_attributes)

    # Reaches source conservés (hors upstream/downstream)
    # Correction pour Python 3.13 
    src_keeped = [
        f for f in src_masked_out
        if not (_geom_equals(f, src_upstream_reach) or _geom_equals(f, src_downstream_reach))
    ]
    write_features(os.path.join(results_dir, "test_src_keeped.shp"), src_keeped, src_schema, src_crs, default_attributes)

    # Reaches corrigés 
    write_features(os.path.join(results_dir, "test_new_up_reach.shp"), [upstream_reach], src_schema, src_crs, default_attributes)
    write_features(os.path.join(results_dir, "test_new_dw_reach.shp"), [downstream_reach], src_schema, src_crs, default_attributes)

    # Shapefile complet
    complete_path = os.path.join(results_dir, "test_complete.shp")
    with fiona.open(complete_path, "w", driver="ESRI Shapefile", crs=src_crs, schema=src_schema) as fout:
        fout.write(adapt_feature(upstream_reach, src_schema, default_attributes))
        fout.write(adapt_feature(downstream_reach, src_schema, default_attributes))
        for feature in src_keeped:
            fout.write(adapt_feature(feature, src_schema, default_attributes))
        for feature in rectified_rep_features:
            fout.write(adapt_feature(feature, src_schema, default_attributes))

    logger.info("Traitement terminé sans erreur => Résultats générés dans le répertoire : %s", results_dir)


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Pipeline de production SWORDLE (sélection, correction de la SWORD et export de shapefiles)."
    )
    p.add_argument("--mask", required=True, help="Shapefile masque (polygone)")
    p.add_argument("--sword", required=True, help="Shapefile SWORD (reaches)")
    p.add_argument("--logic", required=False, choices=["1","2"], default="2", help="Choix de la logique pour la sélection amont/aval (1 ou 2). Défaut : 2.")
    p.add_argument("--replacement", required=True, help="Shapefile replacement (TOPAGE)")
    p.add_argument("--default-attributes", required=True, help="JSON des attributs par défaut")
    p.add_argument("--results", required=True, help="Dossier de sortie des shapefiles.")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR","CRITICAL"],
                   help="Niveau de log (défaut: INFO).")
    return p


def main():
    args = build_arg_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # Vérifications de base sur les chemins
    for label, path in [
        ("mask", args.mask),
        ("sword", args.sword),
        ("replacement", args.replacement),
        ("default-attributes", args.default_attributes),
    ]:
        if not os.path.exists(path):
            logging.error("Le chemin fourni pour --%s n'existe pas : %s", label, path)
            sys.exit(1)

    try:
        run_pipeline(
            mask_path=args.mask,
            sword_path=args.sword,
            logic= args.logic,
            replacement_path=args.replacement,
            default_attr_path=args.default_attributes,
            results_dir=args.results.rstrip(os.sep) + os.sep
        )
    except Exception as e:
        logging.exception("Échec du pipeline : %s", str(e))
        sys.exit(2)


if __name__ == "__main__":
    main()
