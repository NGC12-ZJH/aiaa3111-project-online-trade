# taxonomy_v1 全量标签与质量检查

> `v1_finalize_labels.py` 生成。最终标签 = R6（主方法 R2 配置）；200 个金标准商品使用人工标签。

| 检查 | 结果 | 门槛 / 说明 |
|---|---|---|
| R5 多写法一致（子类） | 91.8%（596 个多写法商品） | ≥ 90% → 通过 ✅ |
| R5 多写法一致（大类） | 94.5% | 只报告 |
| R6 覆盖 | 4724 / 4724 | 缺失 0 个 |
| 不合法输出（记为 other） | 1 | — |
| 人工标签：金标准 / 评测后人工修正 | 200 / 30 | 修正记为 human_override，LLM 原始输出保留在 llm_tag_l2 |
| other 占比（按商品 / 按购买加权） | 1.3% / 0.2% | ≤ 5% → 通过 ✅ |
| 编码前缀家族内一致 | 90.9%（384 个家族） | 只报告；v0 为 91.4% |
| 同名系列内一致（如 TOAST ITS） | 90.6%（32 个系列） | 只报告 |
| 金标准 200 个：LLM 与人工一致 | 90.0% | 应与 R2 的 90.0% 相同（同一缓存） |
| 与 v0 的大类一致 | 79.9% | 只作参考 |
| 用到的子类数 / 最大子类占购买比例 | 77 / 6.7% | — |
| 人工复核清单（最热门 1,000 个中有疑问的） | 20 个 | `results/v1_review_list.csv` |

## 最大的 15 个子类（按 Discovery 购买）

| 大类 | 子类 | 商品数 | 购买占比 |
|---|---|---|---|
| home_decor | hanging_ornaments（悬挂装饰（含圣诞树挂饰）） | 306.0 | 6.7% |
| candles_lighting | candle_holder_lantern（烛台和灯笼） | 186.0 | 4.2% |
| home_decor | wall_signs（墙面标牌） | 66.0 | 3.2% |
| bags | jumbo_shopper_bag（大号购物袋） | 44.0 | 3.1% |
| stationery_gift_wrap | pens_pencils_art（笔和美术用品） | 108.0 | 3.0% |
| baking_party | bunting_garland（彩旗和花环） | 70.0 | 2.8% |
| kitchen_dining | mugs_cups（杯子和马克杯） | 135.0 | 2.7% |
| home_decor | trinket_jewellery_box（首饰盒与小饰品盒） | 110.0 | 2.7% |
| stationery_gift_wrap | gift_wrap_tags（礼品包装纸和标签） | 105.0 | 2.7% |
| personal_care | sewing_craft（缝纫和手工艺套装） | 81.0 | 2.4% |
| kitchen_dining | kitchen_storage（厨房储物罐） | 100.0 | 2.3% |
| stationery_gift_wrap | greeting_cards（贺卡与明信片） | 123.0 | 2.2% |
| home_decor | hot_water_bottle（热水袋） | 34.0 | 2.2% |
| baking_party | cake_cases（蛋糕纸托） | 27.0 | 2.1% |
| baking_party | party_tableware（派对餐具） | 51.0 | 2.0% |

## R5：不同写法得到不同子类的商品（前 30 个）

| 编码 | 各写法的标签 |
|---|---|
| 17107D | FLOWER FAIRY 5 DRAWER LINERS → incense；FLOWER FAIRY 5 SUMMER DRAW LINERS → incense；FLOWER FAIRY,5 SUMMER B'DRAW LINERS → cake_cases |
| 20750 | RED RETROSPOT MINI CASES → trinket_jewellery_box；RED/WHITE DOT MINI CASES → travel_bags_luggage |
| 20754 | RETRO RED SPOTTY WASHING UP GLOVES → clothing_slippers；RETROSPOT RED WASHING UP GLOVES → kitchen_tools |
| 20914 | SET/5 RED RETROSPOT LID GLASS BOWLS → kitchen_storage；SET/5 RED SPOTTY LID GLASS BOWLS → bowls |
| 21530 | DAIRY MAID CERAMIC TOASTRACK → tableware_sets；DAIRY MAID TOASTRACK → kitchen_tools |
| 21531 | RED RETROSPOT SUGAR JAM BOWL → bowls；RETRO SPOT SUGAR JAM BOWL → teapot_tea_set |
| 21539 | RED RETROSPOT BUTTER DISH → plates；RETRO SPOTS BUTTER DISH → kitchen_storage |
| 21620 | S/4 ROSE BOTANICAL CANDLE → decorative_candles；SET OF 4 ROSE BOTANICAL CANDLES → dinner_taper_pillar_candles |
| 22080 | RIBBON REEL POLKADOTS → sewing_craft；RIBBON REEL SPOTS DESIGN → gift_wrap_tags |
| 22129 | PARTY CONES CANDY DECORATION → party_bags_supplies；PARTY CONES CANDY TREE DECORATION → hanging_ornaments |
| 22168 | ORGANISER WOOD ANTIQUE WHITE → furniture_knobs；ORGANISER WOOD, ANTIQUE WHITE → storage_baskets_decor |
| 22175 | PINK OWL DECORATION → tabletop_decorations；PINK OWL SOFT TOY → soft_toys |
| 22176 | BLUE OWL DECORATION → tabletop_decorations；BLUE OWL SOFT TOY → soft_toys |
| 22252 | BIRDCAGE DECORATION MAGIC GARDEN → tabletop_decorations；BIRDCAGE DECORATION TEALIGHT HOLDER → candle_holder_lantern |
| 22359 | GLASS JAR KINGS CHOICE → kitchen_storage；GLASS JAR, KINGS CHOICE SOAP → bath_beauty |
| 22406 | MONEY BOX KINGS CHOICE DESIGN → money_boxes；TIN CAN KINGS CHOICE DESIGN → kitchen_storage |
| 22408 | MONEY BOX CONFECTIONERY DESIGN → money_boxes；TIN CAN CONFECTIONERY DESIGN → kitchen_storage |
| 22409 | MONEY BOX BISCUITS DESIGN → money_boxes；TIN CAN BISCUITS DESIGN → kitchen_storage |
| 22410 | MONEY BOX HOUSEKEEPING DESIGN → money_boxes；TIN CAN HOUSEKEEPING DESIGN → kitchen_storage |
| 22416 | 36 DOILIES SPACEBOY DESIGN → coasters_placemats；SET OF 36 DOILIES SPACEBOY DESIGN → coasters_placemats；SET OF 36 SPACEBOY PAPER DOILIES → party_tableware |
| 22529 | MAGIC DRAWING SLATE GO TO THE FAIR → chalkboards_memo_boards；MAGIC SLATE GO TO THE FAIR → pens_pencils_art |
| 22533 | MAGIC DRAWING SLATE BAKE A CAKE → chalkboards_memo_boards；MAGIC SLATE BAKE A CAKE → pens_pencils_art |
| 22535 | MAGIC DRAWING SLATE BUNNIES → chalkboards_memo_boards；MAGIC SLATE BUNNIES AT HOME → pens_pencils_art |
| 22536 | MAGIC DRAWING SLATE FIDO → chalkboards_memo_boards；MAGIC DRAWING SLATE PURDEY → pens_pencils_art；MAGIC SLATE FIDO → chalkboards_memo_boards |
| 22579 | WOODEN TREE CHRISTMAS SCANDINAVIAN → hanging_ornaments；WOODEN TREE CHRISTMAS SCANDISPOT → tabletop_decorations |
| 22588 | CARD HOLDER GINGHAM HEART → tableware_sets；CARDHOLDER GINGHAM HEART → purse_wallet |
| 22739 | RIBBON REEL CHRISTMAS SOCK BAUBLE → hanging_ornaments；RIBBON REEL, XMAS SOCK/BAUBLE → gift_wrap_tags |
| 22949 | 36 DOILIES DOLLY GIRL → coasters_placemats；SET OF 36 DOLLY GIRL PAPER DOILIES → party_tableware |
| 22950 | 36 DOILIES VINTAGE CHRISTMAS → coasters_placemats；SET OF 36 DOILIES VINTAGE CHRISTMAS → party_tableware；SET OF 36 VINTAGE CHRISTMAS DOILIES → coasters_placemats |
| 22953 | BIRTHDAY BANNER TAPE → gift_wrap_tags；BIRTHDAY PARTY CORDON BARRIER TAPE → party_bags_supplies |