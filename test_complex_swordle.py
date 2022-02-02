import fiona
import json
import os
import pyproj
from shapely.geometry import mapping, shape
import swordle

#====================================================================================================
# MAIN SETTINGS
#====================================================================================================

sword_dir = "/home/msoviche/Documents/databases/SWORD/V2"

roi = 'nantes' #'ile_cite' #'ramier'

mask_path_ramier = "/home/msoviche/Documents/databases/ramier_mask/masque.shp"
mask_path_ile_cite = "/home/msoviche/Documents/databases/mask_ile_cite/masque.shp"
mask_path_nantes = "/home/msoviche/Documents/databases/mask_nantes/masque.shp"

topage_extraction_path_ramier = "/home/msoviche/Documents/databases/TOPAGE/topage_extractions/topage_ile_ramier/Topage_extraction.shp"
topage_extraction_path_ile_cite = "/home/msoviche/Documents/databases/TOPAGE/topage_extractions/topage_ile_cite/topage_ile_cite.shp"
topage_extraction_path_nantes = "/home/msoviche/Documents/databases/TOPAGE/topage_extractions/topage_nantes/topage_extraction_nantes.shp"

if roi == 'ramier':
    mask_path = mask_path_ramier
    topage_extraction_path = topage_extraction_path_ramier
elif roi == 'ile_cite': 
    mask_path = mask_path_ile_cite
    topage_extraction_path = topage_extraction_path_ile_cite
elif roi == 'nantes':
    mask_path = mask_path_nantes
    topage_extraction_path = topage_extraction_path_nantes
else:
  raise ValueError("Wrong 'roi' parameter")

#====================================================================================================
# 1 - selection of reaches portions in source and replacement layers
#====================================================================================================

# Load mask
mask = shape(fiona.Collection(mask_path, "r")[0]["geometry"])

# Load source (SWORD)
src = fiona.Collection(os.path.join(sword_dir, "shp/EU/eu_sword_reaches_hb23_v2.shp"), "r")
# properties = src.schema["properties"]

# Load replacement (TOPAGE extraction)
rep = fiona.Collection(topage_extraction_path, "r")
print("elements replacement data : ", len(rep))

# Load default attributes
with open("default_attributes_v2.json", "r") as fin:
  default_attributes = json.load(fin)

# Reaches of src out of the mask
src_masked_out = swordle.select_reaches_using_mask(src, mask, where="out")

# Reaches of rep in and out of the mask
rep_masked_in = swordle.select_reaches_using_mask(rep, mask, where="in", crs=rep.crs)
rep_masked_out = swordle.select_reaches_using_mask(rep, mask, where="out", crs=rep.crs)

# Apply default attributes in selected replacement portions
print("- Apply default attributes in/out masked replacement layer")
rep_masked_in = swordle.apply_default_attributes(rep_masked_in, default_attributes)
rep_masked_out = swordle.apply_default_attributes(rep_masked_out, default_attributes)

#====================================================================================================
# 2 - fitting source and replacement reaches at the edges of the mask
#====================================================================================================

pairs = swordle.get_matching_src_rep_reaches_using_mask(src_masked_out, rep_masked_out, mask, 4)

print("> len pairs ! ", len(pairs))



# fout = fiona.open("results/test_complex_swordle.shp", "w", 
#                   driver=src.driver,
#                   crs = src.crs,
#                   schema = src.schema)
# for pair in pairs:
#     for feature in pair:
#         fout.write(feature)

# # Keeped reaches from rep
# fout = fiona.open("results/test_complex_rep_masked_out.shp", "w", 
#                   driver=src.driver,
#                   crs = src.crs,
#                   schema = src.schema)
# for feature in rep_masked_out:
#     fout.write(feature)

# # Keeped reaches from rep
# fout = fiona.open("results/test_complex_src_masked_out.shp", "w", 
#                   driver=src.driver,
#                   crs = src.crs,
#                   schema = src.schema)
# for feature in src_masked_out:
#     fout.write(feature)