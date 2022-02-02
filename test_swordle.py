import fiona
import json
import os
import pyproj
from shapely.geometry import mapping, shape
import swordle

#====================================================================================================
# MAIN SETTINGS
#====================================================================================================

#sword_dir = "/home/msoviche/Documents/databases/SWORD/V2"

#roi = 'ramier' #'ile_cite' #'ramier'

#mask_path_ramier = "/home/msoviche/Documents/databases/ramier_mask/masque.shp"
#mask_path_ile_cite = "/home/msoviche/Documents/databases/mask_ile_cite/masque.shp"

#topage_extraction_path_ramier = "/home/msoviche/Documents/databases/TOPAGE/topage_extractions/topage_ile_ramier/Topage_extraction.shp"
#topage_extraction_path_ile_cite = "/home/msoviche/Documents/databases/TOPAGE/topage_extractions/topage_ile_cite/topage_ile_cite.shp"
sword_dir = "/media/kevin/Elements/DATABASES/SWORD/V2"

roi = 'ile_cite' #'ile_cite' #'ramier'

mask_path_ramier = "/home/kevin/Documents/CS/PROJETS/AT_SWOT_Debits/work/PREPARATION_CALVAL/BDRIVER/RAMIER/masque.shp"
mask_path_ile_cite = "/home/msoviche/Documents/databases/mask_ile_cite/masque.shp"

topage_extraction_path_ramier = "/home/kevin/Documents/CS/PROJETS/AT_SWOT_Debits/work/PREPARATION_CALVAL/BDRIVER/RAMIER/Topage_extraction.shp"
topage_extraction_path_ile_cite = "/home/msoviche/Documents/databases/TOPAGE/topage_extractions/topage_ile_cite/topage_ile_cite.shp"

if roi == 'ramier':
  mask_path = mask_path_ramier
  topage_extraction_path = topage_extraction_path_ramier
elif roi == 'ile_cite':
  mask_path = mask_path_ile_cite
  topage_extraction_path = topage_extraction_path_ile_cite
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

# Finding upstream and downstream reaches - Two reaches of source data that will be corrected to fit replacement data in ROI
src_upstream_reach, src_downstream_reach = swordle.find_upstream_downstream_reaches_using_mask(src_masked_out, mask)

# Finding closest intersection points to the mask between src up/dn data and rep data 
upstream_intersection_point = swordle.find_closest_intersection_point_to_the_mask(rep_masked_out, src_upstream_reach, mask)
downstream_intersection_point = swordle.find_closest_intersection_point_to_the_mask(rep_masked_out, src_downstream_reach, mask)

# Corrected upstream and downstream reaches
upstream_reach = swordle.correct_reach_using_intersection_point(
  rep = rep_masked_out,
  src_reach = src_upstream_reach,
  intersection_point = upstream_intersection_point,
  mask = mask
)

downstream_reach = swordle.correct_reach_using_intersection_point(rep = rep_masked_out, 
                                                                  src_reach = src_downstream_reach,
                                                                  intersection_point = downstream_intersection_point,
                                                                  mask = mask)

# #====================================================================================================
# # 3 - Adjusting reach positions of replacement layer inside mask - EN CHANTIER
# #====================================================================================================

rectified_rep_features, upstream_reach, downstream_reach = swordle.adjust_reaches_with_confluence_using_mask(rep_masked_in, upstream_reach, downstream_reach, mask)

# Apply default attributes to elements to save
rectified_rep_features = swordle.apply_default_attributes(rectified_rep_features, default_attributes)

upstream_reach['properties'] = default_attributes
downstream_reach['properties'] = default_attributes

#====================================================================================================
# 4 - Saving
#====================================================================================================

if not os.path.isdir("results"):
    os.makedirs("results")

# Keeped reaches from rep
fout = fiona.open("results/test_rep_masked_out.shp", "w", 
                  driver=src.driver,
                  crs = src.crs,
                  schema = src.schema)
for feature in rep_masked_out:
    fout.write(feature)

# Keeped reaches from rep
fout = fiona.open("results/test_rep_masked_in.shp", "w", 
                  driver=src.driver,
                  crs = src.crs,
                  schema = src.schema)
for feature in rep_masked_in:
    fout.write(feature)

# Keeped reaches from rep
fout = fiona.open("results/test_src_masked_out.shp", "w", 
                  driver=src.driver,
                  crs = src.crs,
                  schema = src.schema)
for feature in src_masked_out:
    fout.write(feature)

# Saving separate elements
# Intersection Points
fout = fiona.open("results/test_points.shp", "w", 
                  driver=src.driver,
                  crs = src.crs, 
                  schema = {'geometry': 'Point',
                            'properties': {}})
for feature in [upstream_intersection_point, downstream_intersection_point]:
    fout.write({'geometry' : mapping(feature), 
                'properties' : {}})

# Src upstream reach
fout = fiona.open("results/test_src_up_reach.shp", "w", 
                  driver=src.driver,
                  crs = src.crs,
                  schema = src.schema)
fout.write(src_upstream_reach)

# Src downstream reach
fout = fiona.open("results/test_src_dw_reach.shp", "w", 
                  driver=src.driver,
                  crs = src.crs,
                  schema = src.schema)
fout.write(src_downstream_reach)

# Keeped reaches from rep
fout = fiona.open("results/test_rep_keeped.shp", "w", 
                  driver=src.driver,
                  crs = src.crs,
                  schema = src.schema)
for feature in rectified_rep_features:
    fout.write(feature)

# Keeped reaches from src
fout = fiona.open("results/test_src_keeped.shp", "w", 
                  driver=src.driver,
                  crs = src.crs,
                  schema = src.schema)
for feature in src_masked_out:
    if (feature != src_downstream_reach) and (feature != src_upstream_reach):
        fout.write(feature)

# Corrected upstream and downstream reaches 
fout = fiona.open("results/test_new_up_reach.shp", "w", 
                  driver=src.driver,
                  crs = src.crs,
                  schema = src.schema)
fout.write(upstream_reach)

fout = fiona.open("results/test_new_dw_reach.shp", "w", 
                  driver=src.driver,
                  crs = src.crs,
                  schema = src.schema)
fout.write(downstream_reach)

# # # fout = fiona.open("results/test_confluence_points.shp", "w", 
# # #                   driver=src.driver,
# # #                   crs = src.crs, 
# # #                   schema = {'geometry': 'MultiPoint',
# # #                             'properties': {}})
# # # fout.write({'geometry' : mapping(confluence_points), 
# # #                 'properties' : {}})

# # #-------------------------------------------------------------------------------------

# Saving full corrected reaches layer 

fout = fiona.open("results/test_complete.shp", "w",
                  driver=src.driver,
                  crs = src.crs,
                  schema = src.schema)

# Saving corrected upstream and downstream reaches
fout.write(upstream_reach)
fout.write(downstream_reach)             

# Saving keeped src reaches
for feature in src_masked_out:
    if (feature != src_downstream_reach) and (feature != src_upstream_reach):
        fout.write(feature)

# Saving keeped rep reaches
for feature in rectified_rep_features:
    fout.write(feature)
