# LLM 打标签轮次比较：R1, R2

> `compare_runs.py` 生成；不需要人工标签。一致率不是准确率，准确率要等人工金标准。

## 各轮概况

| 轮次 | 商品数 | 不合法 | other（按商品） | other（按购买加权） | 置信度中位数 | 置信度 < 0.7 | 新花费（美元） |
|---|---|---|---|---|---|---|---|
| R1 | 200 | 0 | 1.5% | 0.0% | 0.98 | 0 | 0.523 |
| R2 | 200 | 0 | 2.0% | 0.4% | 0.95 | 8 | 0.660 |

## 轮次两两一致率（子类 L2 / 大类 L1）

| 比较 | L2 一致 | L1 一致 | L2 一致（热门 100） | L2 一致（长尾 100） |
|---|---|---|---|---|
| R1 vs R2 | 86.0% | 89.5% | 86.0% | 86.0% |

## 与 v0 对照（只作参考，v0 未经验证）

| 轮次 | L1 一致 | L2 一致（只算 v1 中沿用 v0 id 的子类） |
|---|---|---|
| R1 | 83.0% | 89.2%（n=120） |
| R2 | 77.5% | 76.7%（n=120） |

## R1 vs R2：不一致的商品（共 28 个）

| 编码 | 商品名 | R1 | R2 |
|---|---|---|---|
| 21114 | LAVENDER SCENTED FABRIC HEART | hanging_ornaments | incense |
| 21121 | SET/10 RED SPOTTY PARTY CANDLES | party_bags_supplies | decorative_candles |
| 21122 | SET/10 PINK SPOTTY PARTY CANDLES | party_bags_supplies | decorative_candles |
| 21208 | PASTEL COLOUR HONEYCOMB FAN | bunting_garland | party_bags_supplies |
| 21209 | MULTICOLOUR HONEYCOMB FAN | bunting_garland | hanging_ornaments |
| 21222 | SET/4 BADGES BEETLES | party_bags_supplies | jewellery |
| 21329 | DINOSAURS WRITING SET | notebooks_journals | greeting_cards |
| 21592 | RETRO SPOT CIGAR BOX MATCHES | trinket_jewellery_box | other |
| 21717 | EASTER TIN BUCKET | garden_outdoor | storage_baskets_decor |
| 22227 | DECORATION, HANGING HEART+MIRROR | mirrors | hanging_ornaments |
| 22297 | HEART IVORY TRELLIS SMALL | hanging_ornaments | garden_outdoor |
| 22344 | PARTY PIZZA DISH PINK WHITE SPOT | party_bags_supplies | plates |
| 22444 | GROW YOUR OWN PLANT IN A CAN | garden_outdoor | vases_planters |
| 22525 | CHILDRENS GARDEN GLOVES PINK | garden_outdoor | clothing_slippers |
| 22531 | MAGIC DRAWING SLATE CIRCUS PARADE | pens_pencils_art | chalkboards_memo_boards |
| 22567 | 20 DOLLY PEGS RETROSPOT | sewing_craft | household_laundry_storage |
| 22592 | CARDHOLDER HOLLY WREATH METAL | tabletop_decorations | tableware_sets |
| 22594 | CHRISTMAS GINGHAM TREE | tabletop_decorations | hanging_ornaments |
| 22622 | BOX OF VINTAGE ALPHABET BLOCKS | games_puzzles | word_blocks_letters |
| 22947 | WOODEN ADVENT CALENDAR RED | hanging_ornaments | tabletop_decorations |
| 23008 | DOLLY GIRL BABY GIFT SET | clothing_slippers | soft_toys |
| 23118 | PARISIENNE JEWELLERY DRAWER | furniture_knobs | trinket_jewellery_box |
| 47563B | WAVELINE SURF IRONING BOARD COVER | other | household_laundry_storage |
| 75013B | STRING OF 8 BUTTERFLIES,PINK | hanging_ornaments | bunting_garland |
| 84823 | DANISH ROSE FOLDING CHAIR | furniture_knobs | other |
| 84836 | ZINC METAL HEART DECORATION | hanging_ornaments | tabletop_decorations |
| 84946 | ANTIQUE SILVER TEA GLASS ETCHED | mugs_cups | candle_holder_lantern |
| 85089 | CANDY SPOT BUNNY | egg_cups | soft_toys |