import enum


class Role(enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"


class UserStatus(enum.Enum):
    # Convidado: ainda não definiu a senha pelo link do convite.
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
