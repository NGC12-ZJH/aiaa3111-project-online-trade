# 金标准人工标注一致性：A vs D

> `gold_agreement.py` 生成。只比较两位标注人，不涉及任何机器标签。κ = Cohen's kappa（扣除碰巧一致后的一致程度；> 0.8 以上通常视为很好，0.6–0.8 较好）。“宽松一致”= 一方的答案等于另一方的答案或第二选择。

## 1. 一致率

| 范围 | 商品数 | 子类一致 | 子类 κ | 大类一致 | 大类 κ | 宽松一致（含第二选择） | 按购买量加权的子类一致 |
|---|---|---|---|---|---|---|---|
| 全部 200 | 200 | 92.5% | 0.923 | 95.0% | 0.940 | 99.0% | 94.3% |
| 热门 100 | 100 | 93.0% | 0.927 | 97.0% | 0.963 | 99.0% | 94.2% |
| 长尾 100 | 100 | 92.0% | 0.917 | 93.0% | 0.917 | 99.0% | 94.8% |

## 2. 不确定标记

- A 标了 51 个不确定，D 标了 41 个；A 用了 0 次 other，D 用了 0 次。

| 情况 | 商品数 | 子类一致 |
|---|---|---|
| 两人都确定 | 146 | 100.0% |
| 只有一人不确定 | 16 | 100.0% |
| 两人都不确定 | 38 | 60.5% |

## 3. 分歧最多的子类对

| 子类 1 | 子类 2 | 次数 |
|---|---|---|
| bunting_garland（彩旗和花环） | hanging_ornaments（悬挂装饰（含圣诞树挂饰）） | 2 |
| sewing_craft（缝纫和手工艺套装） | soft_toys（毛绒玩具） | 2 |
| greeting_cards（贺卡与明信片） | pens_pencils_art（笔和美术用品） | 1 |
| kitchen_tools（厨房工具和餐具） | stickers_tattoos（贴纸和纹身贴） | 1 |
| household_laundry_storage（家居洗衣收纳） | jumbo_shopper_bag（大号购物袋） | 1 |
| hanging_ornaments（悬挂装饰（含圣诞树挂饰）） | party_bags_supplies（派对袋和派对用品） | 1 |
| hanging_ornaments（悬挂装饰（含圣诞树挂饰）） | tabletop_decorations（桌面装饰） | 1 |
| games_puzzles（游戏和拼图） | playsets_figurines（游戏套装和玩偶） | 1 |
| clothing_slippers（服装、鞋袜与扇子） | gift_boxes（礼品盒） | 1 |
| hooks_racks_shelves（挂钩、挂架和搁板） | kitchen_storage（厨房储物罐） | 1 |
| kitchen_textiles（厨房与餐桌纺织品） | kitchen_tools（厨房工具和餐具） | 1 |
| garden_outdoor（花园户外装饰） | hooks_racks_shelves（挂钩、挂架和搁板） | 1 |
| soft_toys（毛绒玩具） | tabletop_decorations（桌面装饰） | 1 |

分歧涉及的大类（每个分歧计两次）：家居装饰 8，玩具 5，文具与礼品包装 4，厨房餐饮 4，烘焙与派对 3，包袋 2，个人护理与手工 2，服饰配件 1，园艺户外 1

## 4. 全部分歧（15 个，交 C 裁定）

| 编码 | 商品写法 | A | A 不确定/第二选择 | D | D 不确定/第二选择 | 层 |
|---|---|---|---|---|---|---|
| 21208 | PASTEL COLOUR HONEYCOMB FAN | bunting_garland | 是 → hanging_ornaments | hanging_ornaments | 是 → party_bags_supplies | tail_rule |
| 21209 | MULTICOLOUR HONEYCOMB FAN | bunting_garland | 是 → hanging_ornaments | hanging_ornaments | 是 → party_bags_supplies | tail_rule |
| 21329 | DINOSAURS WRITING SET | pens_pencils_art | 是 → notebooks_journals | greeting_cards | 是 → pens_pencils_art | head |
| 21357 | TOAST ITS - DINOSAUR | stickers_tattoos | 是 → notebooks_journals | kitchen_tools | 是 → baking_tools | tail_cluster_majority |
| 21931 | JUMBO STORAGE BAG SUKI | household_laundry_storage | 是 → storage_baskets_decor | jumbo_shopper_bag | 是 → household_laundry_storage | head |
| 22130 | PARTY CONE CHRISTMAS DECORATION | hanging_ornaments | 是 → party_bags_supplies | party_bags_supplies | 是 → hanging_ornaments | head |
| 22603 | CHRISTMAS RETROSPOT TREE WOOD | tabletop_decorations | 是 → hanging_ornaments | hanging_ornaments | 是 → tabletop_decorations | head |
| 22622 | BOX OF VINTAGE ALPHABET BLOCKS | games_puzzles | 是 → word_blocks_letters | playsets_figurines | 是 → word_blocks_letters | head |
| 22750 | FELTCRAFT PRINCESS LOLA DOLL | soft_toys | 是 → sewing_craft | sewing_craft | 是 → soft_toys | head |
| 22751 | FELTCRAFT PRINCESS OLIVIA DOLL | soft_toys | 是 → sewing_craft | sewing_craft | 是 → soft_toys | head |
| 23008 | DOLLY GIRL BABY GIFT SET | clothing_slippers | 是 → gift_boxes | gift_boxes | 是 → clothing_slippers | tail_other |
| 23143 | ZINC WIRE KITCHEN ORGANISER | kitchen_storage | 是 → hooks_racks_shelves | hooks_racks_shelves | 是 → kitchen_storage | tail_cluster_majority |
| 37112 | YELLOW BIRDS FELT DES FOODCOVER | kitchen_textiles | 是 → kitchen_tools | kitchen_tools | 是 → kitchen_textiles | tail_other |
| 47503H | ASS FLORAL PRINT SPIRIT LEVEL | garden_outdoor | 是 → other | hooks_racks_shelves | 是 → garden_outdoor | tail_cluster_majority |
| 85089 | CANDY SPOT BUNNY | tabletop_decorations | 是 → soft_toys | soft_toys | 是 → tabletop_decorations | tail_cluster_majority |