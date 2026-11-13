"""Стартовые типы объектов — создаются каждой новой организации, дальше редактируются свободно."""
PRESET_TYPES = [
    dict(name="Сцена", geometry_kind="polygon", color="#d1495b", layer="zones", icon="stage",
         fields=[dict(type="longtext", key="description", label="Описание"),
                 dict(type="timerange", key="hours", label="Время работы")]),
    dict(name="Станция / стенд", geometry_kind="polygon", color="#1f6feb", layer="activities", icon="booth",
         fields=[dict(type="text", key="owner", label="Организатор"),
                 dict(type="phone", key="staff_phone", label="Телефон для своих", visible_to="staff")]),
    dict(name="Инфостойка", geometry_kind="point", color="#2a9d8f", layer="services", icon="info",
         fields=[dict(type="phone", key="phone", label="Телефон")]),
    dict(name="Вход / выход", geometry_kind="point", color="#14213d", layer="services", icon="door", fields=[]),
    dict(name="Туалет", geometry_kind="point", color="#6c757d", layer="services", icon="wc", fields=[]),
    dict(name="Еда и напитки", geometry_kind="polygon", color="#f4a261", layer="zones", icon="food",
         fields=[dict(type="multiselect", key="kind", label="Что есть",
                      options=["Кофе", "Горячее", "Закуски", "Вегетарианское"])]),
]
