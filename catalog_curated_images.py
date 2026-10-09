"""Install three local real product images for every product variant.

The source URLs below are public product/photo results gathered from web image
search.  Only the downloaded local files are linked to ProductImage records;
the application never depends on remote image URLs or AI-generated assets.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

import django
import requests
from django.core.files.base import ContentFile
from django.core.files.images import get_image_dimensions

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
django.setup()

from django.conf import settings
from myapp.models import ProductImage, ProductVariant


URL_POOLS = {
    "smartphone": [
        "https://images.rawpixel.com/image_800/cHJpdmF0ZS9sci9pbWFnZXMvd2Vic2l0ZS8yMDI0LTAyL3Jhd3BpeGVsb2ZmaWNlMTVfYV9zdGlsbF9saWZlX3Bob3Rvc2hvdF9vZl9hX21hdHRlX3NtYXJ0X3Bob25lX18wNjU2MTdlNi04NTE1LTRkODUtYWVmNy02NzJkNjdhMTFhNGRfMS5qcGc.jpg",
        "https://i.ebayimg.com/images/g/CC4AAOSwveVltDad/s-l1600.png",
        "https://mpuniquemultiservive.com/assets/product-phone-BfzYe6UB.jpg",
        "https://st2.depositphotos.com/1001735/42320/i/450/depositphotos_423206502-stock-photo-black-mobile-smartphone-blank-screen.jpg",
        "https://content2.rozetka.com.ua/goods/images/big/317170215.jpg",
    ],
    "laptop": [
        "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?q=80&w=1000&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?q=80&w=1000&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1588702545922-e6ee54332b72?q=80&w=1000&auto=format&fit=crop",
        "https://sammanpc.com/cdn/shop/collections/used-laptops-jordan-amman_webp.png?v=1783950069",
        "https://p.globalsources.com/IMAGES/PDT/B1191602737/Laptop.jpg",
    ],
    "tablet": [
        "https://st2.depositphotos.com/16888564/42894/i/450/depositphotos_428940742-stock-photo-modern-black-tablet-isolated-white.jpg",
        "https://i5.walmartimages.com/asr/b15579f3-d1d1-45aa-86ca-2c37169fd306.65bb7452826389d84b400157329eea59.jpeg?odnBg=FFFFFF&odnHeight=900&odnWidth=900",
        "https://images5.tanganetwork.com/prod?bucket=tanga-images&filename=98ff5c367e85.jpeg&height=900&quality=90&width=900",
        "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?q=80&w=1000&auto=format&fit=crop",
        "https://www.mikronis.hr/_shop/files/products/39361-2965_PastedPicture_2025_04_03_1319.jpg?id=2220378%3Fpreset%3Dproduct-fullsize",
    ],
    "console": [
        "https://images.unsplash.com/photo-1486401899868-0e435ed85128?auto=format&fit=crop&fm=jpg&q=80&w=1000",
        "https://i5.walmartimages.com/asr/46417a9c-6119-4dd8-acf1-9368346301d6.8ca917e8a32e96ba18f7525915687afa.jpeg?odnBg=FFFFFF&odnHeight=900&odnWidth=900",
        "https://store.ops.blackbox.com.sa/media/webps/jpg/media/catalog/product/b/l/black_box_53__11zon.webp",
        "https://ifdesign.com/ifservice/5967/310477/00000000-0000-0000-0000-000000000000/02_ps5_02.jpg",
        "https://cdn.mos.cms.futurecdn.net/UV8e8gxMeHA3bDEzate5LZ.jpg",
    ],
    "game_box": [
        "https://memorylanegames.co.nz/cdn/shop/files/7560022-anthem-playstation-4-front-cover.jpg?v=1742813943&width=1200",
        "https://scr.wfcdn.de/22055/Spiele-aus-der-Big-Box-Collection-1589793662-0-0.jpg",
        "https://game-alley.com/cdn/shop/files/DSC_4207.jpg?v=1772730818&width=1200",
        "https://assets.pawnamerica.com/ProductImages/344aa388-5f91-414d-abf8-4b6039671d8d.JPG",
        "https://assets.pawnamerica.com/ProductImages/380edb64-bd49-4f32-91fb-6cdee5f83488.jpg",
        "https://static.xtralife.com/conversions/Y3C1-KP47408797-medium_w640_h480_q75-switchxenoblade3-1659087257.png",
    ],
    "charger": [
        "https://assets.kmart.com.au/transform/417f72aa-7a53-4414-9255-5e1b6465389b/43367535-2?io=transform%3Afit%2Cwidth%3A1200%2Cheight%3A1200&quality=90",
        "https://kmartau.mo.cloudinary.net/09b41d65-7d6c-419c-b0a5-fa7ff3996f69.jpg?tx=w_1200%2Ch_1200",
        "https://image.shoplc.com/products/89/0/8900253/8900253_4.jpg?h=1200&w=1200",
        "https://www.sum-products.com/cdn/shop/products/SR301343.3_1800x1800.jpg?v=1605823927",
        "https://www.belkin.com/dw/image/v2/BGBH_PRD/on/demandware.static/-/Sites-master-product-catalog-blk/default/dw4f5014ff/images/hi-res/3/47445443fec52015_WIA003xx-BLK_APL_BoostCharge_WirelessChargingPad_10W_3-4_WEB.png?sh=700&sm=fit&sw=700",
    ],
    "cable": [
        "https://cdn.dsmcdn.com/mnresize/400/-/ty1245/product/media/images/prod/SPM/PIM/20240406/11/e248a5a0-53ec-3260-b90a-362c2ed9bc05/1_org_zoom.jpg",
        "https://assets.dam.weidmueller.com/assets/api/548fb3a4-d435-4863-aa64-ac104e1f70ce/DAP_Master_PP%2Cw_800%2Cq_80",
        "https://images.unsplash.com/photo-1625842268584-8f3296236761?q=80&w=1000&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1583863788434-e58a36330cf0?q=80&w=1000&auto=format&fit=crop",
    ],
    "headset": [
        "https://i5.walmartimages.com/seo/HyperX-Cloud-II-Wired-Gaming-Headset-Gunmetal_445ad2df-a7d9-4e6e-be79-152795f0667b.fedee6f302db3026ee5d42c41a323a7a.jpeg",
        "https://djd1xqjx2kdnv.cloudfront.net/photos/32/39/445383_16873_XL.jpg",
        "https://hyperx.com/cdn/shop/files/hyperx_cloud_blue_66x0568a_main_1_1370x.jpg?v=1763563224",
        "https://i.ebayimg.com/images/g/gbAAAOSwVx5oKpwN/s-l500.jpg",
        "https://cdn.dsmcdn.com/ty450/product/media/images/20220611/14/124434628/498257597/4/4_org_zoom.jpg",
        "https://s3-apw.badencloud.store/49882-cdn/84fca5ba-2712-4807-a35e-0b52699ced50_0_1687885329.jpg",
    ],
    "smartwatch": [
        "https://images.unsplash.com/photo-1617043786394-f977fa12eddf?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1000",
        "https://busqy.app/products/smartwatch.webp",
        "https://assets.kmart.com.au/transform/812082c7-ea95-4d1e-a929-62df8205ff8a/43527533-1?io=transform%3Afit%2Cwidth%3A1200%2Cheight%3A1200&quality=90",
        "https://sashagift.com/assets/admin/images/backend_images/products/large/24838.png",
        "https://caseguru.ru/upload/caseguru.landing/3be/00v07j3naqgjpwfk4gsf0txqzk305p4l/Frame-5061.png",
        "https://fitnessshoppen.dk/images/ASG4457_BLACK-p.jpg",
    ],
    "vr": [
        "https://shreethemes.in/supero/layouts/assets/images/vr/3.jpg",
        "https://tetco.sa/sites/default/files/2023-06/VR%20-%20%D8%AF%D8%A7%D8%AE%D9%84%D9%8A%20%D9%88%D8%AE%D8%A7%D8%B1%D8%AC%D9%8A.png",
        "https://www.sabic.com/en/Images/SABIC%20VR%20AR%20360%20virtual%20reality%20glasses%20cardboard%20for%20mobile%20phone%20photo%20high%20res_tcm1010-42210_w1024_n.jpeg",
        "https://i5.walmartimages.com/asr/a09fddec-a9c1-4459-a4ab-1011788228b3.14b582a8451387465d530e6cd8f9f0e0.jpeg",
        "https://m.media-amazon.com/images/I/31Qwocnh4TL.jpg",
    ],
    "glasses": [
        "https://static.wixstatic.com/media/3c8c3b_60fc075c3769460db22bd8358b43b599~mv2.png/v1/fill/w_1536%2Ch_1024%2Cal_c%2Cq_90%2Cenc_avif%2Cquality_auto/3c8c3b_60fc075c3769460db22bd8358b43b599~mv2.png",
        "https://cloudfront-us-east-1.images.arcpublishing.com/infobae/EMKXYZEH3ZA6PI4FRYQCH7F2B4.jpg",
        "https://solosglasses.com/cdn/shop/articles/1_3_17bba25f-78a7-411a-8a76-d34c3004448b.png?v=1773040826",
        "https://global.lawaken.com/cdn/shop/files/4_a1224962-dd0a-4a41-ab05-0cc2209ef96b.png?v=1763053480&width=1946",
        "https://gomagcdn.ro/domains/dualstore.ro/files/product/original/ochelari-inteligenti-isen-g300-protectie-uv-inregistrare-fotografiere-traducere-reducere-zgomot-control-tactil-muzica-si-apeluri-activare-vocala-wifi-384072.png",
    ],
    "perfume": [
        "https://a.cdnsbn.com/images/products/l/14452880206-2.jpg",
        "https://www.colorsglass.com/Uploads/products/2021-09-23/en-H94d91d0628284ca79c0ba28530b226edo.jpg",
        "https://amfragrances.com/cdn/shop/files/50mlBlackSquarebottle.png?v=1784227952&width=1066",
        "https://sensabeauty.com/cdn/shop/products/YSLYLEPARFUM2.0OZ.jpg?v=1682958806&width=1000",
        "https://essenza-nobile.de/media/image/product/320858/md/unum-lavs~3.jpg",
    ],
    "skincare": [
        "https://growthkz.online/images/white-background-product-shot.jpg",
        "https://images.squarespace-cdn.com/content/v1/654d7d8df3ed4b721f0dd43d/1755763550430-NTJVZLRCL2DWZH7FJ3BZ/unsplash-image-W71jxsXrwyQ.jpg",
        "https://images.ctfassets.net/97ilwkjto2yr/5hTIW8B8d3AdxazfJuSfzQ/dfa6e8fb89501b0d358148f079c71547/skincare_products_MAIN.jpg",
        "https://cnbthailand.com/static/images/products/skin-care/moisturizer/moisturizer-03.jpg",
        "https://cshpharmacy.com.pk/cdn/shop/files/skincare-category-csh-pharmacy-cerostech_-lahore-online-ecommerce-medicines.jpg?v=1769560306&width=1100",
    ],
    "makeup": [
        "https://lazzda.com/cdn/shop/collections/makeup_663e5987-22c2-48e0-9c79-365f30768e73.png?v=1776062911",
        "https://www.outfitrealm.com/assets/travel-beauty-products-q7AqiW3J.jpg",
        "https://cms-media.fda.moph.go.th/461115214646091776/2023/04/jM951fGgtuMhqJ6eruWhWPLM.jpg",
        "https://www.cbo.cn/data/attachment/image/20240418/20240418100157_11369.png",
        "https://wips.plug.it/cips/video.virgilio.it/cms/2023/06/video_bc6127645758001.jpg?a=r&w=754",
    ],
    "figure": [
        "https://m.media-amazon.com/images/I/41aAdGU8M4L._SS1000_.jpg",
        "https://i5.walmartimages.com/asr/3f41c369-20e3-4ce6-82a0-5815bd294d2b.e8f8649438512558d625bff72fd276c8.jpeg",
        "https://photos.enjoei.com.br/boneco-homem-de-ferro-marvel-universe-era-heroica-11-cm-b54/1200xN/czM6Ly9waG90b3MuZW5qb2VpLmNvbS5ici9wcm9kdWN0cy8xMDg0NTk2LzNlOTFmYWYxNGJlNGJjZWJjZmM4YmQ4MDNmZDFhMTIwLmpwZw",
        "https://images.stockx.com/images/Medicom-Mafex-The-Amazing-Spider-Man-No-001-Action-Figure.jpg?auto=compress&bg=FFFFFF&dpr=2&fit=fill&fm=webp&h=600&q=80&trim=color&updated_at=1631043785&w=800",
        "https://cdn.s7.shopdisney.eu/is/image/DisneyStoreES/417138283173",
    ],
    "board_game": [
        "https://www.asdesjeux.com/cdn/shop/files/gloomhaven-2nd-edition-en-jeux-strategie-strategie-avance-1197016385.webp?v=1760053553&width=1000",
        "https://www.toysrus.com/cdn/shop/files/xlRNR495_01.jpg?v=1721449032&width=1200",
        "https://www.boardgamesindia.com/image/cache/catalog/product/5466-500x500.jpg",
        "https://image.jimcdn.com/app/cms/image/transf/dimension%3D1070x10000%3Aformat%3Djpg/path/sd2ace4e268f33611/image/i64c844de584bcc55/version/1566512252/image.jpg",
        "https://samstoy.in/cdn/shop/files/buy-splendor-game-ahmedabad-gujarat-box-side-view.jpg?v=1749561703&width=1200",
    ],
    "educational": [
        "https://cdn.27.ua/sc--media--prod/default/4f/62/c9/4f62c9d0-4737-4387-b1fe-1c1a79fdad96.jpg",
        "https://areyougame.com/cdn/shop/products/xlLER3813_02.jpg?v=1621104036",
        "https://www.toysrus.com/cdn/shop/files/765023808261_2.jpg?v=1717092235&width=1200",
        "https://imgs.michaels.com/127dd913-7a67-4ed1-a2b3-59f5171eaece.jpg",
        "https://noteonline.pt/cdn/shop/files/7834972_1_1024x.jpg?v=1739293771",
    ],
    "bottle": [
        "https://ridekanuga.com/wp-content/uploads/2022/06/stainless-steel-water-bottle-white-17oz-back-62acb296923b4.jpg",
        "https://echosupplies.com.au/cdn/shop/files/PS2012-WHITE.jpg?v=1758030096&width=1200",
        "https://fashionpyramid.co/cdn/shop/files/53a5bfc8c3f83b7863cc7e9800976150.jpg?v=1730559762&width=900",
        "https://proworksbottles.com/cdn/shop/products/AllWhite_750ml_Personalised_Main_Image_WEB_1020px_800x.png?v=1670601972",
        "https://images.unsplash.com/photo-1602143407151-7111542de6e8?q=80&w=1000&auto=format&fit=crop",
    ],
    "organizer": [
        "https://www.hema.com/dw/image/v2/BBRK_PRD/on/demandware.static/-/Sites-HEMA-master-catalog/default/dwff8a15c7/product/14870040_01_001.jpg?bgcolor=FFFFFF&sfrm=png&sw=1600",
        "https://ae01.alicdn.com/kf/HTB1q7hqainrK1Rjy1Xcq6yeDVXaZ.jpg",
        "https://m.media-amazon.com/images/I/419OCyFSfPL._AC_US750_.jpg",
        "https://masumin.co.tz/cdn/shop/files/320293965-1_1024x.jpg?v=1702462212",
        "https://www.restockit.com/cdn/shop/files/15078397.jpg?v=1741279190",
    ],
    "clogs": [
        "https://xcdn.next.co.uk/common/items/default/default/itemimages/3_4Ratio/product/lge/E77015s4.jpg?im=Resize",
        "https://0990b9.a-cdn.akinoncloud.com/products/2022/05/24/386770/51a662a1-2f25-4134-94d6-ee2e89fa882f.jpg",
        "https://i1.adis.ws/i/truworths/prod3237628_1.jpeg",
        "https://worldbalance.ph/cdn/shop/files/WBHOVERGLIDEMOFF-WHITE_6.jpg?v=1737085741&width=1800",
        "https://xcdn.next.co.uk/common/items/default/default/itemimages/3_4Ratio/product/lge/E77015s5.jpg?im=Resize%2Cwidth%3D750",
        "https://i5.walmartimages.com/seo/Dr-Scholl-s-Dance-On-White-Slip-On-Buckle-Strap-Block-Heel-Rounded-Toe-Clogs-White-9_342b1812-7f07-4620-a2a8-8816696ad9cc.ac6ef991d2a1847d9e18c484feb8ab1a.jpeg",
    ],
    "tomatoes": [
        "https://greentomato.club/cdn/shop/products/GT-Cherry-Vine.png?v=1652866365&width=1200",
        "https://classicfinefoods.co.uk/20643-large_default/red-cherry-tomato.jpg",
        "https://cdn.freshful.ro/media/cache/sylius_shop_product_original/43/3a/69bddbe45cbfbf69f242070a29da.jpg",
        "https://fruitboxco.com/cdn/shop/products/Cherry_tomato_800x.jpg?v=1579689319",
        "https://www.serfrut.cl/cdn/shop/files/tomatecherry.jpg?v=1703633386&width=1200",
    ],
    "spinach": [
        "https://www.bioiberica.com/sites/default/files/landings/daogest/images/histamine-images/spinach-histamine-image.jpg",
        "https://www.graines-bocquet.fr/modules/tvcmsblog/views/img/large-epinard.jpg",
        "https://vicinitymart.com/cdn/shop/products/fresh_Spinach_Box.jpg?v=1758045876",
        "https://cdn.auchan.fr/media/A0220200514000245544PRIMARY_2048x2048/B2CD/?format=rw&height=1200&quality=75&width=1200",
        "https://cdn.metro-cc.ru/ru/ru_pim_300047001001_01.png",
    ],
    "curry": [
        "https://www.jamoona.com/cdn/shop/files/50g-Frische-Karee-Patta--Curryblaetter--9018417.png?v=1753253285",
        "https://www.healthbenefitstimes.com/9/gallery/curry-leaves/Curry-leaves.jpg",
        "https://www.bbassets.com/media/uploads/p/xl/10000105-5_3-fresho-curry-leaves.jpg",
        "https://dukaan.b-cdn.net/700x700/webp/upload_file_service/asg/b118e1de-962f-43b3-92db-ae06362e8ed5/CurryLeaves.png",
        "https://desigros.com/cdn/shop/files/curry-leaf.png?v=1745591933&width=1000",
    ],
}


def pool_key(variant):
    name = variant.product.name.lower()
    category = variant.product.category.name.lower()
    if "vegetable" in category:
        return "curry" if "curry" in name else "spinach"
    if "gaming" in category and "retro" in name:
        return "console"
    if "gaming" in category and not any(word in name for word in ("headset", "controller", "gamepad", "watch", "console")):
        return "game_box"
    if "curry" in name:
        return "curry"
    if "spinach" in name:
        return "spinach"
    if "tomato" in name:
        return "tomatoes"
    if "clog" in name or "footwear" in category:
        return "clogs"
    if "organizer" in name:
        return "organizer"
    if "bottle" in name:
        return "bottle"
    if "figure" in name:
        return "figure"
    if "board game" in name or "strategy game" in name:
        return "board_game"
    if "stem" in name or "science" in name or "robotics" in name:
        return "educational"
    if "console" in name:
        return "console"
    if "game" in name or "racing" in name or "adventure" in name:
        return "game_box"
    if "vr" in name:
        return "vr"
    if "glass" in name:
        return "glasses"
    if "headset" in name or "headphone" in name:
        return "headset"
    if "controller" in name or "gamepad" in name:
        return "console"
    if "perfume" in name or "parfum" in name or "toilette" in name:
        return "perfume"
    if "cream" in name or "serum" in name:
        return "skincare"
    if "lip" in name or "palette" in name or "compact" in name:
        return "makeup"
    if "watch" in name or "band" in name or "wearable" in category:
        return "smartwatch"
    if "charger" in name or "charging" in name or "cable" in name:
        return "cable" if "cable" in name else "charger"
    if "tablet" in name or "ipad" in name or "tab " in name:
        return "tablet"
    if "laptop" in name or "notebook" in name or "book" in name or "lenovo" in name:
        return "laptop"
    if "phone" in name or "iphone" in name or "mobile" in name or "mobiles" in name:
        return "smartphone"
    return "smartphone"


def download(session, url):
    response = session.get(url, timeout=60, headers={"Accept": "image/*,*/*;q=0.8"})
    response.raise_for_status()
    if not response.headers.get("Content-Type", "").lower().startswith("image/"):
        return None
    if len(response.content) < 10_000:
        return None
    try:
        width, height = get_image_dimensions(ContentFile(response.content))
    except Exception:
        return None
    if not width or not height or width < 250 or height < 250:
        return None
    return response.content, response.headers.get("Content-Type", "image/jpeg").split(";", 1)[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start", type=int, default=0)
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": "EEHookCatalog/1.0"})
    variants = list(ProductVariant.objects.order_by("id"))
    variants = variants[args.start : args.start + args.limit if args.limit else None]
    prepared = []
    failures = []
    cache = {}

    for index, variant in enumerate(variants, 1):
        key = pool_key(variant)
        urls = URL_POOLS[key]
        start = (variant.id * 3) % len(urls)
        candidates = urls[start:] + urls[:start]
        selected = []
        hashes = set()
        for url in candidates:
            if url not in cache:
                try:
                    cache[url] = download(session, url)
                except Exception as error:
                    print(f"  download failed: {error}", file=sys.stderr)
                    cache[url] = None
            result = cache[url]
            if not result:
                continue
            content, content_type = result
            digest = hashlib.sha256(content).hexdigest()
            if digest in hashes:
                continue
            hashes.add(digest)
            selected.append((content, content_type, url))
            if len(selected) == 3:
                break
        if len(selected) != 3:
            failures.append((variant.id, variant.product.name, key, len(selected)))
            print(f"[{index}/{len(variants)}] FAIL {variant.id} {key}: {len(selected)}/3")
        else:
            print(f"[{index}/{len(variants)}] OK {variant.id} {key}")
            prepared.append((variant, selected))

    if failures:
        print("Failures:")
        for failure in failures:
            print(" | ".join(map(str, failure)))
        return 2
    if not args.apply:
        print(f"Dry run passed for {len(variants)} variants.")
        return 0

    destination = Path(settings.MEDIA_ROOT) / "products" / "verified_real"
    destination.mkdir(parents=True, exist_ok=True)
    for variant, selected in prepared:
        ProductImage.objects.filter(variant=variant).delete()
        for position, (content, content_type, _source) in enumerate(selected):
            extension = {"image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
            filename = f"variant-{variant.id}-{position + 1}-{hashlib.sha1(content).hexdigest()[:12]}.{extension}"
            image = ProductImage(variant=variant, position=position, is_primary=position == 0)
            image.image.save(filename, ContentFile(content), save=False)
            image.save()
    print(f"Applied exactly 3 local real images to {len(prepared)} variants.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
