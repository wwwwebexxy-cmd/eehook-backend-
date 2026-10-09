import os
import django

import traceback


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
    django.setup()

    from myapp.models import Cart, Wishlist
    from myapp.serializers import CartSerializer, WishlistSerializer

    print("--- Testing Cart Serializer ---")
    try:
        cart = Cart.objects.all()
        data = CartSerializer(cart, many=True).data
        print("Cart Serializer Success. Data length:", len(data))
    except Exception:
        print("Cart Serializer Error:")
        traceback.print_exc()

    print("\n--- Testing Wishlist Serializer ---")
    try:
        wishlist = Wishlist.objects.all()
        data = WishlistSerializer(wishlist, many=True).data
        print("Wishlist Serializer Success. Data length:", len(data))
    except Exception:
        print("Wishlist Serializer Error:")
        traceback.print_exc()


if __name__ == "__main__":
    main()
