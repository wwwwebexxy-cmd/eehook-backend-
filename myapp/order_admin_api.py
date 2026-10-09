from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import AdminAuditLog, Order
from .permissions import IsSuperAdmin
from .serializers import OrderSerializer


class OrderAdminPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_size_query_param = "page_size"

    def get_page_size(self, request):
        size = super().get_page_size(request)
        return min(size or self.page_size, self.max_page_size)


class OrderListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=100)
    status = serializers.ChoiceField(required=False, choices=Order.STATUS_CHOICES)
    payment_status = serializers.ChoiceField(
        required=False, choices=Order.PAYMENT_STATUS_CHOICES
    )
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    ordering = serializers.ChoiceField(
        required=False,
        choices=(
            ("-created_at", "Newest"),
            ("created_at", "Oldest"),
            ("-total_amount", "Highest amount"),
            ("total_amount", "Lowest amount"),
        ),
        default="-created_at",
    )

    def validate(self, attrs):
        if attrs.get("date_from") and attrs.get("date_to"):
            if attrs["date_from"] > attrs["date_to"]:
                raise serializers.ValidationError(
                    {"date_to": "date_to must be on or after date_from."}
                )
        return attrs


class OrderAdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ("status", "payment_status", "address")

    def validate_address(self, address):
        if address and not address.user_id == self.instance.user_id:
            raise serializers.ValidationError(
                "The address must belong to the order's customer."
            )
        return address


class SuperAdminOrderListView(generics.ListAPIView):
    permission_classes = (IsSuperAdmin,)
    pagination_class = OrderAdminPagination
    serializer_class = OrderSerializer

    def get_queryset(self):
        query = OrderListQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data

        orders = (
            Order.objects.select_related("user", "address")
            .prefetch_related("items__product", "items__color", "items__unit")
            .all()
        )

        search = params.get("search", "").strip()
        if search:
            filters = (
                Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(stripe_session_id__icontains=search)
            )
            if search.upper().startswith("ORD-"):
                search = search[4:].lstrip("0") or "0"
            if search.isdigit():
                filters |= Q(pk=int(search))
            orders = orders.filter(filters)

        if params.get("status"):
            orders = orders.filter(status=params["status"])
        if params.get("payment_status"):
            orders = orders.filter(payment_status=params["payment_status"])
        if params.get("date_from"):
            orders = orders.filter(created_at__date__gte=params["date_from"])
        if params.get("date_to"):
            orders = orders.filter(created_at__date__lte=params["date_to"])

        return orders.order_by(params.get("ordering", "-created_at"), "-id")


class SuperAdminOrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsSuperAdmin,)
    queryset = Order.objects.select_related("user", "address").prefetch_related(
        "items__product", "items__color", "items__unit"
    )
    lookup_url_kwarg = "id"
    serializer_class = OrderSerializer

    def update(self, request, *args, **kwargs):
        # Both PUT and PATCH are accepted for dashboard clients that send only
        # the fields they are changing (for example, status alone).
        partial = True
        order = self.get_object()
        input_serializer = OrderAdminUpdateSerializer(
            order, data=request.data, partial=partial
        )
        input_serializer.is_valid(raise_exception=True)
        previous_status = order.status
        input_serializer.save()
        AdminAuditLog.objects.create(
            admin_user=request.user,
            action="update",
            entity_type="order",
            entity_id=str(order.pk),
            description=f"Order updated from status {previous_status}.",
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return Response(self.get_serializer(order).data)

    def destroy(self, request, *args, **kwargs):
        order = self.get_object()
        if order.status != "Cancelled":
            order.status = "Cancelled"
            from django.utils import timezone
            order.cancelled_at = timezone.now()
            order.cancelled_by = request.user
            order.save(update_fields=("status", "cancelled_at", "cancelled_by", "updated_at"))
            AdminAuditLog.objects.create(
                admin_user=request.user,
                action="cancel",
                entity_type="order",
                entity_id=str(order.pk),
                description="Order cancelled from the admin dashboard.",
                ip_address=request.META.get("REMOTE_ADDR"),
            )
        return Response(
            {"message": "Order cancelled.", "order": self.get_serializer(order).data},
            status=status.HTTP_200_OK,
        )
