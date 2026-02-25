#!/usr/bin/env python3
"""
C# Source Code Parser for AI Code Generation System
Layer > Genre > Role > Tag 분류 체계 적용
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

# ============================================================
# Configuration
# ============================================================

ROLE_PATTERNS = {
    'Manager': [r'.*Manager$'],
    'Controller': [r'.*Controller$'],
    'Calculator': [r'.*Calculator$', r'.*Calc$'],
    'Processor': [r'.*Processor$'],
    'Handler': [r'.*Handler$'],
    'Listener': [r'.*Listener$'],
    'Provider': [r'.*Provider$'],
    'Factory': [r'.*Factory$'],
    'Service': [r'.*Service$'],
    'Validator': [r'.*Validator$'],
    'Converter': [r'.*Converter$'],
    'Builder': [r'.*Builder$'],
    'Pool': [r'.*Pool$', r'.*Pooler$'],
    'State': [r'.*State$'],
    'Command': [r'.*Command$', r'.*Cmd$'],
    'Observer': [r'.*Observer$'],
    'Helper': [r'.*Helper$', r'.*Util$', r'.*Utils$', r'.*Utility$'],
    'Wrapper': [r'.*Wrapper$'],
    'Context': [r'.*Context$', r'.*Ctx$'],
    'Config': [r'.*Config$', r'.*Settings$', r'.*Configuration$'],
    'UX': [r'.*Effect$', r'.*Tweener$', r'.*Performer$', r'.*Presenter$', r'.*Particle$'],
}

LAYER_KEYWORDS = {
    'Core': ['Singleton', 'Pool', 'Event', 'Util', 'Extension', 'Base', 'Common', 'Framework'],
    'Game': ['Page', 'Popup', 'Win', 'Element', 'HUD', 'Panel', 'Dialog', 'Toast', 'Component'],
}

GENRE_KEYWORDS = {
    'RPG': ['Battle', 'Combat', 'Character', 'Enemy', 'Boss', 'Skill', 'Buff', 'Damage', 'Item', 'Quest', 'Dungeon', 'Raid', 'Equipment', 'Inventory'],
    'Idle': ['Idle', 'Offline', 'AutoPlay', 'AFK', 'Prestige', 'Rebirth'],
    'Merge': ['Merge', 'Combine', 'Grid', 'Cell', 'Generator'],
    'SLG': ['Strategy', 'Territory', 'Troop', 'Alliance', 'War'],
    'Tycoon': ['Business', 'Revenue', 'Customer', 'Staff', 'Shop', 'Store', 'Money', 'Profit'],
    'Simulation': ['Resource', 'Building', 'Construct', 'Timer', 'Production'],
    'Puzzle': ['Board', 'Piece', 'Match', 'Tile', 'Combo', 'Puzzle'],
}

MAJOR_TAG_PATTERNS = {
    'StateControl': [r'^(Start|Begin|Init|Enter|End|Stop|Exit|Finish|Spawn|Despawn|Create|Destroy|Set|Apply|Update|Change|Switch)'],
    'ValueModification': [r'^(Calculate|Compute|Calc|Add|Increase|Plus|Remove|Decrease|Minus|Multiply|Divide)'],
    'ConditionCheck': [r'^(Get|Find|Search|Check|Validate|Is|Can|Has|Compare|Match)'],
    'ResourceTransfer': [r'^(Transfer|Move|Send|Receive|Consume|Spend|Earn|Gain)'],
    'DataSync': [r'^(Save|Load|Sync|Serialize|Deserialize|Store|Restore|Cache)'],
    'FlowControl': [r'^(Wait|Delay|Pause|Resume|Continue|Loop|Iterate|ForEach|Process)'],
    'ResponseTrigger': [r'^(On|Handle|Notify|Trigger|Fire|Emit|Broadcast|Publish|Subscribe)'],
}

MINOR_TAG_PATTERNS = {
    'Compare': [r'Compare', r'Equals', r'Match'],
    'Calculate': [r'Calculate', r'Compute', r'Calc', r'Add', r'Remove', r'Multiply'],
    'Find': [r'Get', r'Find', r'Search', r'Lookup', r'Query'],
    'Validate': [r'Validate', r'Check', r'Is', r'Can', r'Has', r'Verify'],
    'Assign': [r'Set', r'Assign', r'Apply', r'Update', r'Init'],
    'Notify': [r'Notify', r'On', r'Handle', r'Trigger', r'Fire', r'Emit'],
    'Delay': [r'Wait', r'Delay', r'Pause', r'Sleep', r'Coroutine'],
    'Spawn': [r'Spawn', r'Create', r'Instantiate', r'Generate', r'Make', r'New'],
    'Despawn': [r'Despawn', r'Destroy', r'Remove', r'Delete', r'Kill', r'Dispose'],
    'Iterate': [r'ForEach', r'Iterate', r'Loop', r'Process', r'Traverse'],
    'Aggregate': [r'Sum', r'Count', r'Total', r'Aggregate', r'Collect', r'Gather'],
}

# Unity lifecycle methods to exclude from 'uses'
UNITY_LIFECYCLE = {'Awake', 'Start', 'Update', 'FixedUpdate', 'LateUpdate',
                   'OnEnable', 'OnDisable', 'OnDestroy', 'OnApplicationPause',
                   'OnApplicationQuit', 'OnGUI', 'OnTriggerEnter', 'OnTriggerExit',
                   'OnCollisionEnter', 'OnCollisionExit'}

COMMON_METHODS = {'Init', 'Initialize', 'Refresh', 'Reset', 'Clear', 'Dispose',
                  'ToString', 'GetHashCode', 'Equals', 'GetType'}

PRIMITIVE_TYPES = {'int', 'float', 'double', 'string', 'bool', 'void', 'byte',
                   'short', 'long', 'char', 'decimal', 'object', 'var', 'dynamic'}

UNITY_TYPES = {'MonoBehaviour', 'ScriptableObject', 'GameObject', 'Transform',
               'Component', 'Behaviour', 'Object', 'Coroutine', 'IEnumerator'}

# ============================================================
# Data Classes
# ============================================================

@dataclass
class MethodInfo:
    methodName: str
    accessModifier: str
    returnType: str
    parameters: List[Dict]
    signature: str
    isStatic: bool = False
    isVirtual: bool = False
    isOverride: bool = False
    isAsync: bool = False
    isCoroutine: bool = False
    majorTag: str = ""
    minorTag: str = ""

@dataclass
class FieldInfo:
    fieldName: str
    fieldType: str
    accessModifier: str
    isStatic: bool = False
    isReadonly: bool = False
    hasSerializeField: bool = False
    initialValue: Optional[str] = None

@dataclass
class PropertyInfo:
    propertyName: str
    propertyType: str
    accessModifier: str
    hasGetter: bool = False
    hasSetter: bool = False

@dataclass
class ClassInfo:
    className: str
    classType: str  # class, struct, enum, interface
    accessModifier: str
    isPartial: bool = False
    isAbstract: bool = False
    isStatic: bool = False
    baseClass: Optional[str] = None
    interfaces: List[str] = field(default_factory=list)
    role: str = "Component"
    fields: List[FieldInfo] = field(default_factory=list)
    properties: List[PropertyInfo] = field(default_factory=list)
    methods: List[MethodInfo] = field(default_factory=list)

@dataclass
class FileInfo:
    fileId: str
    filePath: str
    namespace: str
    layer: str
    genre: str
    role: str
    system: str
    score: float
    usings: List[str] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)
    uses: List[str] = field(default_factory=list)
    usedBy: List[str] = field(default_factory=list)

# ============================================================
# Parser Class
# ============================================================

class CSharpParser:
    def __init__(self, default_genre: str = "Generic"):
        self.default_genre = default_genre

    def parse_file(self, file_path: str, relative_path: str) -> Optional[FileInfo]:
        """Parse a single C# file"""
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return None

        # Extract basic info
        file_name = os.path.basename(file_path)
        file_id = os.path.splitext(file_name)[0]

        # Parse components
        usings = self._extract_usings(content)
        namespace = self._extract_namespace(content)
        classes = self._extract_classes(content)

        if not classes:
            return None

        # Determine classifications
        main_class = classes[0] if classes else None
        role = self._determine_role(file_id, main_class)
        layer = self._determine_layer(file_id, relative_path, main_class)
        genre = self._determine_genre(file_id, relative_path, content)
        system = self._determine_system(relative_path, file_id)

        # Extract dependencies
        uses = self._extract_uses(content, file_id)
        provides, requires = self._extract_contract(classes)

        return FileInfo(
            fileId=file_id,
            filePath=relative_path,
            namespace=namespace,
            layer=layer,
            genre=genre,
            role=role,
            system=system,
            score=0.4,  # Initial score
            usings=usings,
            classes=classes,
            provides=provides,
            requires=requires,
            uses=uses,
            usedBy=[]  # Will be calculated later
        )

    def _extract_usings(self, content: str) -> List[str]:
        """Extract using statements"""
        pattern = r'using\s+([\w.]+)\s*;'
        return re.findall(pattern, content)

    def _extract_namespace(self, content: str) -> str:
        """Extract namespace"""
        pattern = r'namespace\s+([\w.]+)'
        match = re.search(pattern, content)
        return match.group(1) if match else ""

    def _extract_classes(self, content: str) -> List[ClassInfo]:
        """Extract class definitions"""
        classes = []

        # Pattern for class/struct/interface/enum
        pattern = r'(public|private|protected|internal)?\s*(partial)?\s*(abstract)?\s*(static)?\s*(class|struct|interface|enum)\s+(\w+)(?:<[^>]+>)?(?:\s*:\s*([^{]+))?'

        for match in re.finditer(pattern, content):
            access = match.group(1) or 'internal'
            is_partial = match.group(2) is not None
            is_abstract = match.group(3) is not None
            is_static = match.group(4) is not None
            class_type = match.group(5)
            class_name = match.group(6)
            inheritance = match.group(7)

            base_class = None
            interfaces = []

            if inheritance:
                parts = [p.strip() for p in inheritance.split(',')]
                for i, part in enumerate(parts):
                    if i == 0 and not part.startswith('I'):
                        base_class = part
                    elif part.startswith('I') and part[1].isupper():
                        interfaces.append(part)
                    elif i == 0:
                        base_class = part

            role = self._determine_role(class_name, None)

            # Extract methods for this class
            methods = self._extract_methods(content, class_name)
            fields = self._extract_fields(content, class_name)
            properties = self._extract_properties(content, class_name)

            classes.append(ClassInfo(
                className=class_name,
                classType=class_type,
                accessModifier=access,
                isPartial=is_partial,
                isAbstract=is_abstract,
                isStatic=is_static,
                baseClass=base_class,
                interfaces=interfaces,
                role=role,
                fields=fields,
                properties=properties,
                methods=methods
            ))

        return classes

    def _extract_methods(self, content: str, class_name: str) -> List[MethodInfo]:
        """Extract method definitions"""
        methods = []

        # Simplified method pattern
        pattern = r'(public|private|protected|internal)\s+(static\s+)?(virtual\s+)?(override\s+)?(async\s+)?([\w<>\[\],\s]+)\s+(\w+)\s*\(([^)]*)\)'

        for match in re.finditer(pattern, content):
            access = match.group(1)
            is_static = match.group(2) is not None
            is_virtual = match.group(3) is not None
            is_override = match.group(4) is not None
            is_async = match.group(5) is not None
            return_type = match.group(6).strip()
            method_name = match.group(7)
            params_str = match.group(8)

            # Skip if it looks like a field or property
            if method_name in ['get', 'set', 'value']:
                continue

            # Parse parameters
            parameters = []
            if params_str.strip():
                for param in params_str.split(','):
                    param = param.strip()
                    if param:
                        parts = param.split()
                        if len(parts) >= 2:
                            parameters.append({
                                'paramType': ' '.join(parts[:-1]),
                                'paramName': parts[-1]
                            })

            signature = f"{return_type} {method_name}({params_str})"
            is_coroutine = return_type == 'IEnumerator'

            # Determine tags
            major_tag = self._determine_major_tag(method_name)
            minor_tag = self._determine_minor_tag(method_name)

            methods.append(MethodInfo(
                methodName=method_name,
                accessModifier=access,
                returnType=return_type,
                parameters=parameters,
                signature=signature,
                isStatic=is_static,
                isVirtual=is_virtual,
                isOverride=is_override,
                isAsync=is_async,
                isCoroutine=is_coroutine,
                majorTag=major_tag,
                minorTag=minor_tag
            ))

        return methods

    def _extract_fields(self, content: str, class_name: str) -> List[FieldInfo]:
        """Extract field definitions (class level only)"""
        fields = []

        # Pattern for fields (with SerializeField support)
        pattern = r'(\[SerializeField\]\s*)?(public|private|protected|internal)\s+(static\s+)?(readonly\s+)?([\w<>\[\],\s]+)\s+(\w+)\s*(?:=\s*([^;]+))?\s*;'

        # Find class body
        class_pattern = rf'(class|struct)\s+{class_name}[^{{]*\{{'
        class_match = re.search(class_pattern, content)
        if not class_match:
            return fields

        # Track brace depth to only get class-level fields
        start = class_match.end()
        depth = 1
        i = start
        class_body_start = start
        class_body_end = start

        while i < len(content) and depth > 0:
            if content[i] == '{':
                depth += 1
            elif content[i] == '}':
                depth -= 1
            i += 1
        class_body_end = i

        class_body = content[class_body_start:class_body_end]

        for match in re.finditer(pattern, class_body):
            has_serialize = match.group(1) is not None
            access = match.group(2)
            is_static = match.group(3) is not None
            is_readonly = match.group(4) is not None
            field_type = match.group(5).strip()
            field_name = match.group(6)
            initial_value = match.group(7)

            # Skip if looks like method parameter
            if field_type in ['return', 'if', 'for', 'while', 'foreach']:
                continue

            fields.append(FieldInfo(
                fieldName=field_name,
                fieldType=field_type,
                accessModifier=access,
                isStatic=is_static,
                isReadonly=is_readonly,
                hasSerializeField=has_serialize,
                initialValue=initial_value.strip() if initial_value else None
            ))

        return fields

    def _extract_properties(self, content: str, class_name: str) -> List[PropertyInfo]:
        """Extract property definitions"""
        properties = []

        # Pattern for properties
        pattern = r'(public|private|protected|internal)\s+(static\s+)?([\w<>\[\],\s]+)\s+(\w+)\s*\{\s*(get;?)?\s*(set;?)?\s*\}'

        for match in re.finditer(pattern, content):
            access = match.group(1)
            prop_type = match.group(3).strip()
            prop_name = match.group(4)
            has_getter = match.group(5) is not None
            has_setter = match.group(6) is not None

            properties.append(PropertyInfo(
                propertyName=prop_name,
                propertyType=prop_type,
                accessModifier=access,
                hasGetter=has_getter,
                hasSetter=has_setter
            ))

        return properties

    def _extract_uses(self, content: str, file_id: str) -> List[str]:
        """Extract class dependencies"""
        uses = set()

        # Type declarations
        type_pattern = r'(?:new\s+|:\s*|<|,\s*)(\w+)(?:<[^>]+>)?(?:\s*[>\(\[\{,]|$)'
        for match in re.finditer(type_pattern, content):
            type_name = match.group(1)
            if self._is_valid_dependency(type_name, file_id):
                uses.add(type_name)

        # Singleton access
        singleton_pattern = r'(\w+)\.Instance'
        for match in re.finditer(singleton_pattern, content):
            type_name = match.group(1)
            if self._is_valid_dependency(type_name, file_id):
                uses.add(type_name)

        # Static method calls
        static_pattern = r'(\w+)\.(\w+)\s*\('
        for match in re.finditer(static_pattern, content):
            type_name = match.group(1)
            method_name = match.group(2)
            if self._is_valid_dependency(type_name, file_id) and method_name not in UNITY_LIFECYCLE:
                uses.add(type_name)

        return sorted(list(uses))

    def _is_valid_dependency(self, type_name: str, file_id: str) -> bool:
        """Check if a type name is a valid dependency"""
        if not type_name or len(type_name) < 2:
            return False
        if type_name == file_id:
            return False
        if type_name.lower() in PRIMITIVE_TYPES:
            return False
        if type_name in UNITY_TYPES:
            return False
        if type_name in UNITY_LIFECYCLE:
            return False
        if type_name in COMMON_METHODS:
            return False
        if not type_name[0].isupper():
            return False
        return True

    def _extract_contract(self, classes: List[ClassInfo]) -> Tuple[List[str], List[str]]:
        """Extract provides/requires contract"""
        provides = []
        requires = []

        for cls in classes:
            # Provides: public methods and properties
            for method in cls.methods:
                if method.accessModifier == 'public':
                    provides.append(method.signature)

            for prop in cls.properties:
                if prop.accessModifier == 'public':
                    if prop.hasGetter:
                        provides.append(f"{prop.propertyType} {prop.propertyName} {{ get; }}")

        return provides[:10], requires[:10]  # Limit for index

    def _determine_role(self, class_name: str, class_info: Optional[ClassInfo]) -> str:
        """Determine role based on class name pattern"""
        for role, patterns in ROLE_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, class_name):
                    return role
        return "Component"

    def _determine_layer(self, file_id: str, path: str, class_info: Optional[ClassInfo]) -> str:
        """Determine layer (Core/Domain/Game)"""
        path_lower = path.lower()
        file_lower = file_id.lower()

        # Check Core keywords
        for keyword in LAYER_KEYWORDS['Core']:
            if keyword.lower() in file_lower or keyword.lower() in path_lower:
                return "Core"

        # Check Game keywords
        for keyword in LAYER_KEYWORDS['Game']:
            if keyword.lower() in file_lower:
                return "Game"

        # Check inheritance
        if class_info and class_info.baseClass:
            base = class_info.baseClass.lower()
            if 'singleton' in base:
                return "Core"
            if any(kw.lower() in base for kw in ['page', 'popup', 'win', 'panel']):
                return "Game"

        return "Domain"

    def _determine_genre(self, file_id: str, path: str, content: str) -> str:
        """Determine genre based on keywords"""
        combined = (file_id + " " + path + " " + content[:1000]).lower()

        scores = {}
        for genre, keywords in GENRE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in combined)
            if score > 0:
                scores[genre] = score

        if scores:
            return max(scores, key=scores.get)

        return self.default_genre

    def _determine_system(self, path: str, file_id: str) -> str:
        """Determine system from folder path"""
        parts = Path(path).parts

        # Skip common folders
        skip = {'Scripts', 'Assets', 'Project', 'PPM', 'IdleMoney'}

        for part in parts:
            if part not in skip and not part.endswith('.cs'):
                return part

        return file_id

    def _determine_major_tag(self, method_name: str) -> str:
        """Determine major tag from method name"""
        for tag, patterns in MAJOR_TAG_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, method_name, re.IGNORECASE):
                    return tag
        return "FlowControl"

    def _determine_minor_tag(self, method_name: str) -> str:
        """Determine minor tag from method name"""
        for tag, patterns in MINOR_TAG_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, method_name, re.IGNORECASE):
                    return tag
        return "Assign"


# ============================================================
# Database Manager
# ============================================================

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.indices = {}  # genre -> layer -> [entries]

    def add_file(self, file_info: FileInfo):
        """Add a parsed file to the database"""
        genre = file_info.genre.lower()
        layer = file_info.layer.lower()

        # Ensure directories exist
        genre_path = self.db_path / 'base' / genre / layer
        files_path = genre_path / 'files'
        files_path.mkdir(parents=True, exist_ok=True)

        # Save full file info
        file_path = files_path / f"{file_info.fileId}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self._to_dict(file_info), f, indent=2, ensure_ascii=False)

        # Update index
        key = (genre, layer)
        if key not in self.indices:
            self.indices[key] = []

        self.indices[key].append({
            'fileId': file_info.fileId,
            'layer': file_info.layer,
            'genre': file_info.genre,
            'role': file_info.role,
            'system': file_info.system,
            'score': file_info.score,
            'provides': file_info.provides[:5],
            'requires': file_info.requires[:5]
        })

    def save_indices(self):
        """Save all indices to files"""
        for (genre, layer), entries in self.indices.items():
            index_path = self.db_path / 'base' / genre / layer / 'index.json'
            index_path.parent.mkdir(parents=True, exist_ok=True)

            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)

    def _to_dict(self, obj) -> dict:
        """Convert dataclass to dict recursively"""
        if hasattr(obj, '__dataclass_fields__'):
            return {k: self._to_dict(v) for k, v in asdict(obj).items()}
        elif isinstance(obj, list):
            return [self._to_dict(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._to_dict(v) for k, v in obj.items()}
        return obj


# ============================================================
# Main
# ============================================================

def parse_project(source_path: str, genre: str, db_path: str):
    """Parse a project and save to database"""
    parser = CSharpParser(default_genre=genre)
    db = DatabaseManager(db_path)

    source_path = Path(source_path)

    stats = {
        'total': 0,
        'parsed': 0,
        'failed': 0,
        'by_layer': {},
        'by_genre': {},
        'by_role': {}
    }

    print(f"\nParsing: {source_path}")
    print(f"Default Genre: {genre}")
    print("-" * 50)

    for cs_file in source_path.rglob('*.cs'):
        # Skip certain folders
        relative = cs_file.relative_to(source_path)
        if any(skip in str(relative) for skip in ['Editor', 'Test', 'Plugins', 'ThirdParty']):
            continue

        stats['total'] += 1

        file_info = parser.parse_file(str(cs_file), str(relative))

        if file_info:
            db.add_file(file_info)
            stats['parsed'] += 1

            # Update stats
            stats['by_layer'][file_info.layer] = stats['by_layer'].get(file_info.layer, 0) + 1
            stats['by_genre'][file_info.genre] = stats['by_genre'].get(file_info.genre, 0) + 1
            stats['by_role'][file_info.role] = stats['by_role'].get(file_info.role, 0) + 1

            if stats['parsed'] % 100 == 0:
                print(f"  Parsed: {stats['parsed']} files...")
        else:
            stats['failed'] += 1

    db.save_indices()

    print("-" * 50)
    print(f"Total: {stats['total']}")
    print(f"Parsed: {stats['parsed']}")
    print(f"Failed: {stats['failed']}")
    print(f"\nBy Layer: {stats['by_layer']}")
    print(f"By Genre: {stats['by_genre']}")
    print(f"By Role: {dict(sorted(stats['by_role'].items(), key=lambda x: -x[1])[:10])}")

    return stats


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("Usage: python parser.py <source_path> <genre> [db_path]")
        print("  genre: rpg, idle, merge, slg, tycoon, simulation, puzzle, generic")
        sys.exit(1)

    source = sys.argv[1]
    genre = sys.argv[2].upper()
    db_path = sys.argv[3] if len(sys.argv) > 3 else "E:/AI/db"

    parse_project(source, genre, db_path)
