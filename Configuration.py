
import json

class _ElementBase:
    _name: str

    def __init__(self):
        ()
        self._name = ""


class _ValueElement(_ElementBase):
    def __init__(self):
        super().__init__()


    def getValue(self):
        ()
        

class _ParentElement(_ElementBase):
    def __init__(self):
        super().__init__()


    def getElement(self, name):
        ()

    def getValue(self, name):
        parts = name.split(".", 1)
        
        element = self.getElement(parts[0])
        if element is None:
            return None
        
        if len(parts) == 1:
            if isinstance(element, _ValueElement):
                return element.getValue()
        else:
            if isinstance(element, _ParentElement):
                return element.getValue(parts[1])

        return None


class Element(_ValueElement):
    _type: type
    _value = None

    def __init__(self):
        super().__init__()

    
    def getValue(self):
        return self._value
    

    def setValue(self, value):
        if not isinstance(value, self._type):
            raise Exception(f"'{value}' does not match type {self._type} of configuration element {self._name}")

        self._value = value
    

    def cloneDefinition(self):
        s = Element()
        s._name = self._name
        s._type = self._type
        s._value = self._value
        return s


class ElementGroup(_ParentElement):
    _items: dict

    def __init__(self):
        super().__init__()
        self._items = {}


    def getElement(self, name):
        if not name in self._items:
            return None
        return self._items[name]
    

    def addElement(self, name, valueType:type=None, defaultValue:any=None):
        if valueType is None:
            if defaultValue is None:
                raise Exception(f"Either an explicit type or a default value must be set for element '{name}'")
            valueType = type(defaultValue)
        
        s = Element()
        s._name = name
        s._type = valueType
        s._value = defaultValue
        self._items[name] = s
        return self


    def addElementGroup(self, name):
        s = ElementGroup()
        s._name = name
        self._items[name] = s
        return s


    def addValueList(self, name, valueType):
        s = ListElement()
        s._name = name
        s._type = valueType
        self._items[name] = s
        return s
    

    def addElementGroupList(self, name):
        s = ElementGroupList()
        s._name = name
        self._items[name]  = s
        return s


    def cloneDefinition(self):
        g = ElementGroup()
        g._name = self._name
        g._items = {}
        for k, v in self._items.items():
            g._items[k] = v.cloneDefinition()
        return g


class ListElement(_ValueElement):
    _items: list
    _type: type

    def __init__(self):
        super().__init__()
        self._items = []


    def count(self):
        return len(self._items)


    def addValue(self, value):
        if not isinstance(value, self._type):
            raise Exception(f"'{value}' does not match type {self._type} of configuration element {self._name}")

        self._items.append(value)

    def setValue(self, n, value):
        if not isinstance(value, self._type):
            raise Exception(f"'{value}' does not match type {self._type} of configuration element {self._name}")

        self._items[n] = value


    def getItem(self, n):
        if (n < 0) or (n >= self.count()):
            return None
        return self._items[n]


    def getValue(self):
        return self._items.copy()


    def cloneDefinition(self):
        s = ElementList()
        s._name = self._name
        s._type = self._type
        return s



class ElementGroupList(_ParentElement):
    _items: list
    _group: ElementGroup

    def __init__(self):
        super().__init__()
        self._items = []

        self._group = ElementGroup()
        self._group.name = '_'


    def count(self):
        return len(self._items)


    def add(self):
        g =  self._group.cloneDefinition()
        g._name = f"[_{len(self._items)}"
        self._items.append(g)
        return g


    def addElement(self, name, valueType:type=None, defaultValue:any=None):
        self._group.addElement(name, valueType, defaultValue)
        return self


    def getItem(self, n):
        if (n < 0) or (n >= self.count()):
            return None
        return self._items[n]


    def getElement(self, name):
        n = int(name)
        return self.getItem(n)


    def cloneDefinition(self):
        s = ElementGroupList()
        s._group = self._group.cloneDefinition()
        return s


class _Configuration(ElementGroup):
    def __init__(self):
        super().__init__()
        self._name = "Configuration"


    def save(self, path):
        d = {}
        self._toDictionary(self, d)
        with open(path, 'w') as f:
            json.dump(d, f)

    
    def load(self, path):
        try:
            d = {}
            with open(path, 'r') as f:
                d = json.load(f)
            
            self._fromDictionary(self, d)
        except (FileNotFoundError, IOError):
            ()


    def update(self, jsonString: str):
        d = json.loads(jsonString)
        self._fromDictionary(self, d)

    
    def toString(self):
        d = {}
        self._toDictionary(self, d)
        return json.dumps(d)

    
    def _toDictionary(self, element, d: dict):
        for item in element._items.values():
            if isinstance(item, ElementGroup):
                elementDict = {}
                self._toDictionary(item, elementDict)
                d[item._name] = elementDict
            
            elif isinstance(item, ElementGroupList):
                elementList = []
                for li in item._items:
                    elementDict = {}
                    self._toDictionary(li, elementDict)
                    elementList.append(elementDict)

                d[item._name] = elementList
            
            elif isinstance(item, ListElement):
                d[item._name] = item.getValue()

            else:
                d[item._name] = item._value


    def _fromDictionary(self, element, d: dict):
        for k, v in d.items():
            child = element.getElement(k)
            if child is None:
                ()

            elif isinstance(child, ElementGroup):
                if isinstance(v, dict):
                    self._fromDictionary(child, v)

            elif isinstance(child, ElementGroupList):
                if isinstance(v, list):
                    child._items.clear()
                    for li in v:
                        if isinstance(li, dict):
                            g = child._group.cloneDefinition()
                            self._fromDictionary(g, li)                            
                            child._items.append(g)
            
            elif isinstance(child, ListElement):
                if isinstance(v, list):
                    child._items.clear()
                    for li in v:
                        if isinstance(li, child._type):
                            child._items.append(li)

            else:
                child.setValue(v)


Configuration = _Configuration()
