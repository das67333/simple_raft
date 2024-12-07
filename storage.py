import enum
import dataclasses
import typing


@enum.unique
class StorageModificationType(enum.Enum):
    CREATE = 1
    UPDATE = 2
    DELETE = 3
    CAS = 4


@dataclasses.dataclass
class StorageModification:
    sn: int
    id: int
    type: StorageModificationType
    value: typing.Optional[str] = None  # for non-DELETE
    old_value: typing.Optional[str] = None  # for CAS

    def asdict(self) -> dict:
        result = {
            'sn': self.sn,
            'id': self.id,
            'type': self.type.name,
        }
        if self.value is not None:
            result['value'] = self.value
        if self.old_value is not None:
            result['old_value'] = self.old_value
        return result

    @staticmethod
    def fromdict(data: dict) -> None:
        return StorageModification(
            sn=data['sn'],
            id=data['id'],
            type=StorageModificationType[data['type']],
            value=data.get('value'),
            old_value=data.get('old_value'),
        )


class DroppedModification(Exception):
    pass


@dataclasses.dataclass
class DetectedGapInLog(DroppedModification):
    sn_from: int


class StorageValue:
    exists: bool = False
    value: typing.Optional[str] = None

    def apply_modification(self, modification: StorageModification):
        # только CREATE неидемпотентный
        if modification.type == StorageModificationType.CREATE and self.exists:
            raise DroppedModification()
        match modification.type:
            case StorageModificationType.CREATE:
                self.exists, self.value = True, modification.value
            case StorageModificationType.UPDATE:
                self.value = modification.value
            case StorageModificationType.DELETE:
                self.exists, self.value = False, None
            case StorageModificationType.CAS:
                if self.value == modification.old_value:
                    self.value = modification.value


class Storage:
    log: typing.List[StorageModification]

    def __init__(self) -> None:
        self.log = []

    def add_modification(self, modification: StorageModification):
        if modification.sn > len(self.log):
            raise DetectedGapInLog(sn_from=len(self.log))
        else:
            self.log.append(modification)
            # проверим, не нарушается ли история изменений
            try:
                self.get_value(m_id=modification.id)
            except DroppedModification:
                self.log.pop()
                raise

    def get_value(self, m_id: int) -> typing.Optional[str]:
        sv = StorageValue()
        for modification in filter(lambda x: x.id == m_id, self.log):
            sv.apply_modification(modification)
        return sv.value

    def generate_sn(self) -> int:
        return len(self.log)
