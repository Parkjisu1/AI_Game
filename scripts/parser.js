#!/usr/bin/env node
/**
 * C# Source Code Parser for AI Code Generation System
 * Layer > Genre > Role > Tag 분류 체계 적용
 * v3.0 - Tag 분류 추가, Generic 자동 분류 개선, index 스키마 확장
 */

const fs = require('fs');
const path = require('path');

// ============================================================
// Configuration
// ============================================================

// Role 패턴 (파일명 기반 - 우선순위 5)
const ROLE_NAME_PATTERNS = {
    'Manager': [/.*Manager$/],
    'Controller': [/.*Controller$/],
    'Calculator': [/.*Calculator$/, /.*Calc$/],
    'Processor': [/.*Processor$/],
    'Handler': [/.*Handler$/],
    'Listener': [/.*Listener$/],
    'Provider': [/.*Provider$/],
    'Factory': [/.*Factory$/],
    'Service': [/.*Service$/],
    'Validator': [/.*Validator$/],
    'Converter': [/.*Converter$/],
    'Builder': [/.*Builder$/],
    'Pool': [/.*Pool$/, /.*Pooler$/],
    'State': [/.*State$/],
    'Command': [/.*Command$/, /.*Cmd$/],
    'Observer': [/.*Observer$/],
    'Helper': [/.*Helper$/, /.*Util$/, /.*Utils$/, /.*Utility$/],
    'Wrapper': [/.*Wrapper$/],
    'Context': [/.*Context$/, /.*Ctx$/],
    'Config': [/.*Config$/, /.*Settings$/, /.*Configuration$/],
    'Message': [/.*Msg$/, /.*Message$/],
    'Data': [/.*Data$/, /.*Info$/, /.*DTO$/],
    'Table': [/.*Table$/],
    'View': [/.*Page$/, /.*Popup$/, /.*Win$/, /.*Window$/, /.*Panel$/, /.*Dialog$/],
    'UX': [/.*Effect$/, /.*Tweener$/, /.*Performer$/, /.*Presenter$/, /.*Particle$/],
};

// 상속 기반 Role (우선순위 2)
const ROLE_BASE_CLASS = {
    'Manager': ['Singleton'],
    'StateHandler': ['StateMachineBehaviour'],
    'Config': ['ScriptableObject'],
    'View': ['UIBase', 'PageBase', 'PopupBase', 'WindowBase', 'PanelBase'],
    'Entity': ['PooledGameObject', 'PooledObject'],
    'Model': ['UserData', 'SaveData'],
};

// 인터페이스 기반 Role (우선순위 3)
const ROLE_INTERFACE = {
    'Message': ['IMessageAction', 'IMessage'],
    'Controller': ['IMessagePort', 'IMessageController'],
    'Service': ['IInjectable', 'IService'],
};

const LAYER_KEYWORDS = {
    'Core': ['Singleton', 'Pool', 'Event', 'Util', 'Extension', 'Base', 'Common', 'Framework'],
    'Game': ['Page', 'Popup', 'Win', 'Element', 'HUD', 'Panel', 'Dialog', 'Toast'],
};

// Domain 강제 키워드 (Core보다 우선)
const DOMAIN_FORCE_KEYWORDS = ['Battle', 'Character', 'Inventory', 'Quest', 'Skill', 'Item', 'Shop', 'Gacha'];

const GENRE_KEYWORDS = {
    'RPG': ['Battle', 'Combat', 'Character', 'Enemy', 'Boss', 'Skill', 'Buff', 'Damage', 'Item', 'Quest', 'Dungeon', 'Raid', 'Equipment', 'Inventory'],
    'Idle': ['Idle', 'Offline', 'AutoPlay', 'AFK', 'Prestige', 'Rebirth'],
    'Merge': ['Merge', 'Combine', 'Grid', 'Cell', 'Generator'],
    'SLG': ['Strategy', 'Territory', 'Troop', 'Alliance', 'War'],
    'Tycoon': ['Business', 'Revenue', 'Customer', 'Staff', 'Shop', 'Store', 'Money', 'Profit'],
    'Simulation': ['Resource', 'Building', 'Construct', 'Timer', 'Production'],
    'Puzzle': ['Board', 'Piece', 'Match', 'Tile', 'Combo', 'Puzzle'],
};

const UNITY_LIFECYCLE = new Set(['Awake', 'Start', 'Update', 'FixedUpdate', 'LateUpdate',
    'OnEnable', 'OnDisable', 'OnDestroy', 'OnApplicationPause',
    'OnApplicationQuit', 'OnGUI', 'OnTriggerEnter', 'OnTriggerExit',
    'OnCollisionEnter', 'OnCollisionExit']);

const COMMON_METHODS = new Set(['Init', 'Initialize', 'Refresh', 'Reset', 'Clear', 'Dispose',
    'ToString', 'GetHashCode', 'Equals', 'GetType']);

// Major Tag patterns (메서드명 prefix → 대기능 Tag)
const MAJOR_TAG_PATTERNS = {
    'StateControl': [/^Start/, /^Begin/, /^Init/, /^Enable/, /^Open/, /^Close/, /^End/, /^Stop/, /^Disable/],
    'ValueModification': [/^Set/, /^Add/, /^Subtract/, /^Multiply/, /^Increase/, /^Decrease/, /^Modify/, /^Change/],
    'ConditionCheck': [/^Check/, /^Is/, /^Has/, /^Can/, /^Validate/, /^Should/],
    'ResourceTransfer': [/^Give/, /^Take/, /^Transfer/, /^Send/, /^Receive/, /^Buy/, /^Sell/],
    'DataSync': [/^Save/, /^Load/, /^Sync/, /^Update/, /^Refresh/, /^Fetch/],
    'FlowControl': [/^Execute/, /^Run/, /^Process/, /^Handle/, /^Do/],
    'ResponseTrigger': [/^On/, /^Respond/, /^React/, /^Trigger/, /^Fire/, /^Emit/]
};

// Minor Tag patterns (메서드명 prefix → 소기능 Tag)
const MINOR_TAG_PATTERNS = {
    'Compare': [/^Compare/, /^Sort/],
    'Calculate': [/^Calculate/, /^Compute/, /^Eval/],
    'Find': [/^Find/, /^Search/, /^Get/, /^Lookup/],
    'Validate': [/^Validate/, /^Verify/, /^Assert/],
    'Assign': [/^Assign/, /^Set/, /^Apply/],
    'Notify': [/^Notify/, /^Publish/, /^Broadcast/, /^Dispatch/],
    'Delay': [/^Wait/, /^Delay/, /^Yield/],
    'Spawn': [/^Spawn/, /^Create/, /^Instantiate/, /^Generate/],
    'Despawn': [/^Despawn/, /^Destroy/, /^Remove/, /^Kill/, /^Delete/],
    'Iterate': [/^ForEach/, /^Iterate/, /^Loop/, /^Traverse/],
    'Aggregate': [/^Sum/, /^Count/, /^Aggregate/, /^Total/, /^Collect/]
};

const PRIMITIVE_TYPES = new Set(['int', 'float', 'double', 'string', 'bool', 'void', 'byte',
    'short', 'long', 'char', 'decimal', 'object', 'var', 'dynamic', 'uint', 'ulong', 'sbyte', 'ushort']);

const UNITY_TYPES = new Set(['MonoBehaviour', 'ScriptableObject', 'GameObject', 'Transform',
    'Component', 'Behaviour', 'Object', 'Coroutine', 'IEnumerator',
    'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Rect', 'Color', 'Color32',
    'Sprite', 'Image', 'Text', 'Button', 'RectTransform', 'Canvas',
    'AudioSource', 'AudioClip', 'Animator', 'Animation', 'Rigidbody', 'Collider',
    'Camera', 'Light', 'Material', 'Texture', 'Texture2D', 'Mesh', 'Shader']);

const COLLECTION_TYPES = new Set(['List', 'Dictionary', 'HashSet', 'Queue', 'Stack',
    'Array', 'IList', 'IDictionary', 'IEnumerable', 'ICollection']);

const SYSTEM_TYPES = new Set(['Action', 'Func', 'Task', 'CancellationToken', 'Exception',
    'Type', 'Attribute', 'EventArgs', 'StringBuilder', 'Regex']);

// ============================================================
// Parser Class
// ============================================================

class CSharpParser {
    constructor(defaultGenre = 'Generic') {
        this.defaultGenre = defaultGenre;
    }

    parseFile(filePath, relativePath) {
        let content;
        try {
            content = fs.readFileSync(filePath, 'utf-8');
            if (content.charCodeAt(0) === 0xFEFF) {
                content = content.slice(1);
            }
        } catch (e) {
            console.error(`Error reading ${filePath}: ${e.message}`);
            return null;
        }

        const fileName = path.basename(filePath);
        const fileId = path.parse(fileName).name;

        const usings = this.extractUsings(content);
        const namespace = this.extractNamespace(content);
        const classes = this.extractClasses(content);

        if (classes.length === 0) {
            return null;
        }

        const mainClass = classes[0];

        // 개선된 Role 분류 (다단계)
        const role = this.determineRoleAdvanced(fileId, mainClass);

        // 개선된 Layer 분류 (Domain 강제 키워드 추가)
        const layer = this.determineLayerAdvanced(fileId, relativePath, mainClass);

        const genre = this.determineGenre(fileId, relativePath, content, layer);
        const system = this.determineSystem(relativePath, fileId);

        const uses = this.extractUses(content, fileId);

        // 개선된 Contract 추출
        const { provides, requires } = this.extractContractAdvanced(classes, content);

        // Tag classification
        const allMethods = classes.reduce((acc, cls) => acc.concat(cls.methods), []);
        const tags = this.classifyClassTags(allMethods);

        return {
            fileId,
            filePath: relativePath,
            namespace,
            layer,
            genre,
            role,
            system,
            score: 0.4,
            usings,
            classes,
            provides,
            requires,
            tags,
            uses,
            usedBy: []
        };
    }

    extractUsings(content) {
        const pattern = /using\s+([\w.]+)\s*;/g;
        const usings = [];
        let match;
        while ((match = pattern.exec(content)) !== null) {
            usings.push(match[1]);
        }
        return usings;
    }

    extractNamespace(content) {
        const pattern = /namespace\s+([\w.]+)/;
        const match = content.match(pattern);
        return match ? match[1] : '';
    }

    extractClasses(content) {
        const classes = [];
        const pattern = /(public|private|protected|internal)?\s*(partial)?\s*(abstract)?\s*(static)?\s*(class|struct|interface|enum)\s+(\w+)(?:<[^>]+>)?(?:\s*:\s*([^{]+))?/g;

        let match;
        while ((match = pattern.exec(content)) !== null) {
            const access = match[1] || 'internal';
            const isPartial = !!match[2];
            const isAbstract = !!match[3];
            const isStatic = !!match[4];
            const classType = match[5];
            const className = match[6];
            const inheritance = match[7];

            let baseClass = null;
            const interfaces = [];

            if (inheritance) {
                const parts = inheritance.split(',').map(p => p.trim());
                for (let i = 0; i < parts.length; i++) {
                    const part = parts[i].split('<')[0].trim(); // Remove generic part for checking
                    const fullPart = parts[i].trim();
                    if (i === 0 && !part.startsWith('I')) {
                        baseClass = fullPart;
                    } else if (part.startsWith('I') && part.length > 1 && part[1] === part[1].toUpperCase()) {
                        interfaces.push(fullPart);
                    } else if (i === 0) {
                        baseClass = fullPart;
                    }
                }
            }

            const methods = this.extractMethods(content, className);
            const fields = this.extractFields(content, className);
            const properties = this.extractProperties(content, className);

            classes.push({
                className,
                classType,
                accessModifier: access,
                isPartial,
                isAbstract,
                isStatic,
                baseClass,
                interfaces,
                fields,
                properties,
                methods
            });
        }

        return classes;
    }

    extractMethods(content, className) {
        const methods = [];
        const pattern = /(public|private|protected|internal)\s+(static\s+)?(virtual\s+)?(override\s+)?(async\s+)?([\w<>\[\],\s]+)\s+(\w+)\s*\(([^)]*)\)/g;

        let match;
        while ((match = pattern.exec(content)) !== null) {
            const access = match[1];
            const isStatic = !!match[2];
            const isVirtual = !!match[3];
            const isOverride = !!match[4];
            const isAsync = !!match[5];
            const returnType = match[6].trim();
            const methodName = match[7];
            const paramsStr = match[8];

            if (['get', 'set', 'value'].includes(methodName)) continue;

            const parameters = [];
            if (paramsStr.trim()) {
                for (const param of paramsStr.split(',')) {
                    const trimmed = param.trim();
                    if (trimmed) {
                        const parts = trimmed.split(/\s+/);
                        if (parts.length >= 2) {
                            parameters.push({
                                paramType: parts.slice(0, -1).join(' '),
                                paramName: parts[parts.length - 1]
                            });
                        }
                    }
                }
            }

            const signature = `${returnType} ${methodName}(${paramsStr})`;
            const isCoroutine = returnType === 'IEnumerator';

            const { majorTag, minorTag } = this.classifyMethodTag(methodName);

            methods.push({
                methodName,
                accessModifier: access,
                returnType,
                parameters,
                signature,
                isStatic,
                isVirtual,
                isOverride,
                isAsync,
                isCoroutine,
                majorTag,
                minorTag
            });
        }

        return methods;
    }

    extractFields(content, className) {
        const fields = [];

        // Find class body
        const classPattern = new RegExp(`(class|struct)\\s+${className}[^{]*\\{`);
        const classMatch = content.match(classPattern);
        if (!classMatch) return fields;

        const start = classMatch.index + classMatch[0].length;
        let depth = 1;
        let i = start;

        while (i < content.length && depth > 0) {
            if (content[i] === '{') depth++;
            else if (content[i] === '}') depth--;
            i++;
        }

        const classBody = content.slice(start, i);

        const fieldPattern = /(\[SerializeField\]\s*|\[Inject\]\s*)?(public|private|protected|internal)\s+(static\s+)?(readonly\s+)?(const\s+)?([\w<>\[\],\s]+)\s+(\w+)\s*(?:=\s*([^;]+))?\s*;/g;

        let match;
        while ((match = fieldPattern.exec(classBody)) !== null) {
            const hasAttribute = !!match[1];
            const attributeType = match[1] ? (match[1].includes('Inject') ? 'Inject' : 'SerializeField') : null;
            const access = match[2];
            const isStatic = !!match[3];
            const isReadonly = !!match[4];
            const isConst = !!match[5];
            const fieldType = match[6].trim();
            const fieldName = match[7];
            const initialValue = match[8];

            if (['return', 'if', 'for', 'while', 'foreach', 'new', 'throw'].includes(fieldType)) continue;

            fields.push({
                fieldName,
                fieldType,
                accessModifier: access,
                isStatic,
                isReadonly,
                isConst,
                hasSerializeField: attributeType === 'SerializeField',
                hasInject: attributeType === 'Inject',
                initialValue: initialValue ? initialValue.trim() : null
            });
        }

        return fields;
    }

    extractProperties(content, className) {
        const properties = [];
        const pattern = /(public|private|protected|internal)\s+(static\s+)?([\w<>\[\],\s]+)\s+(\w+)\s*\{\s*(get;?)?\s*(set;?)?\s*\}/g;

        let match;
        while ((match = pattern.exec(content)) !== null) {
            const access = match[1];
            const propType = match[3].trim();
            const propName = match[4];
            const hasGetter = !!match[5];
            const hasSetter = !!match[6];

            properties.push({
                propertyName: propName,
                propertyType: propType,
                accessModifier: access,
                hasGetter,
                hasSetter
            });
        }

        return properties;
    }

    extractUses(content, fileId) {
        const uses = new Set();

        // Type declarations
        const typePattern = /(?:new\s+|:\s*|<|,\s*)(\w+)(?:<[^>]+>)?(?:\s*[>\(\[\{,]|$)/g;
        let match;
        while ((match = typePattern.exec(content)) !== null) {
            const typeName = match[1];
            if (this.isValidDependency(typeName, fileId)) {
                uses.add(typeName);
            }
        }

        // Singleton access
        const singletonPattern = /(\w+)\.Instance/g;
        while ((match = singletonPattern.exec(content)) !== null) {
            const typeName = match[1];
            if (this.isValidDependency(typeName, fileId)) {
                uses.add(typeName);
            }
        }

        // Static method calls
        const staticPattern = /(\w+)\.(\w+)\s*\(/g;
        while ((match = staticPattern.exec(content)) !== null) {
            const typeName = match[1];
            const methodName = match[2];
            if (this.isValidDependency(typeName, fileId) && !UNITY_LIFECYCLE.has(methodName)) {
                uses.add(typeName);
            }
        }

        return Array.from(uses).sort();
    }

    isValidDependency(typeName, fileId) {
        if (!typeName || typeName.length < 2) return false;
        if (typeName === fileId) return false;
        if (PRIMITIVE_TYPES.has(typeName.toLowerCase())) return false;
        if (UNITY_TYPES.has(typeName)) return false;
        if (COLLECTION_TYPES.has(typeName)) return false;
        if (SYSTEM_TYPES.has(typeName)) return false;
        if (UNITY_LIFECYCLE.has(typeName)) return false;
        if (COMMON_METHODS.has(typeName)) return false;
        if (typeName[0] !== typeName[0].toUpperCase()) return false;
        return true;
    }

    // ============================================================
    // 개선된 Contract 추출
    // ============================================================

    extractContractAdvanced(classes, content) {
        const provides = [];
        const requiresSet = new Set();

        for (const cls of classes) {
            // === Provides: public 메서드/프로퍼티 ===
            for (const method of cls.methods) {
                if (method.accessModifier === 'public') {
                    provides.push(method.signature);
                }
            }

            for (const prop of cls.properties) {
                if (prop.accessModifier === 'public' && prop.hasGetter) {
                    provides.push(`${prop.propertyType} ${prop.propertyName} { get; }`);
                }
            }

            // === Requires 추출 ===

            // 1. 인터페이스 구현
            for (const iface of cls.interfaces) {
                const cleanIface = this.extractTypeName(iface);
                if (this.isValidRequires(cleanIface)) {
                    requiresSet.add(cleanIface);
                }
                // 제네릭 인자도 추출
                const genericArgs = this.extractGenericArgs(iface);
                for (const arg of genericArgs) {
                    if (this.isValidRequires(arg)) {
                        requiresSet.add(arg);
                    }
                }
            }

            // 2. 상속 클래스 (Unity 기본 타입 제외)
            if (cls.baseClass) {
                const baseName = this.extractTypeName(cls.baseClass);
                if (this.isValidRequires(baseName) && !UNITY_TYPES.has(baseName)) {
                    requiresSet.add(baseName);
                }
            }

            // 3. [SerializeField] 또는 [Inject] 필드
            for (const field of cls.fields) {
                if (field.hasSerializeField || field.hasInject) {
                    const typeName = this.extractTypeName(field.fieldType);
                    if (this.isValidRequires(typeName)) {
                        requiresSet.add(typeName);
                    }
                    // 제네릭 인자
                    const genericArgs = this.extractGenericArgs(field.fieldType);
                    for (const arg of genericArgs) {
                        if (this.isValidRequires(arg)) {
                            requiresSet.add(arg);
                        }
                    }
                }
            }

            // 4. Init/Setup/Constructor 메서드 파라미터
            const initMethods = cls.methods.filter(m =>
                ['Init', 'Initialize', 'Setup', 'Configure', 'SetMessageController', 'Construct'].includes(m.methodName)
            );
            for (const method of initMethods) {
                for (const param of method.parameters) {
                    const typeName = this.extractTypeName(param.paramType);
                    if (this.isValidRequires(typeName)) {
                        requiresSet.add(typeName);
                    }
                    const genericArgs = this.extractGenericArgs(param.paramType);
                    for (const arg of genericArgs) {
                        if (this.isValidRequires(arg)) {
                            requiresSet.add(arg);
                        }
                    }
                }
            }

            // 5. 비기본 타입 필드 (public 또는 protected)
            for (const field of cls.fields) {
                if (field.accessModifier === 'public' || field.accessModifier === 'protected') {
                    const typeName = this.extractTypeName(field.fieldType);
                    if (this.isValidRequires(typeName)) {
                        requiresSet.add(typeName);
                    }
                }
            }
        }

        // GetComponent<T> 패턴 추출
        const getComponentPattern = /GetComponent<(\w+)>/g;
        let match;
        while ((match = getComponentPattern.exec(content)) !== null) {
            if (this.isValidRequires(match[1])) {
                requiresSet.add(match[1]);
            }
        }

        return {
            provides: provides.slice(0, 15),
            requires: Array.from(requiresSet).sort().slice(0, 15)
        };
    }

    extractTypeName(fullType) {
        // "List<Something>" -> "List", "Dictionary<K,V>" -> "Dictionary"
        // "IMessageAction<GameMode>" -> "IMessageAction"
        if (!fullType) return '';
        return fullType.split('<')[0].split('[')[0].trim();
    }

    extractGenericArgs(fullType) {
        // "IMessageAction<GameMode>" -> ["GameMode"]
        // "Dictionary<string, UserInfo>" -> ["UserInfo"] (string 제외)
        const args = [];
        const match = fullType.match(/<([^>]+)>/);
        if (match) {
            const parts = match[1].split(',').map(p => p.trim());
            for (const part of parts) {
                const typeName = this.extractTypeName(part);
                if (typeName && !PRIMITIVE_TYPES.has(typeName.toLowerCase())) {
                    args.push(typeName);
                }
            }
        }
        return args;
    }

    isValidRequires(typeName) {
        if (!typeName || typeName.length < 2) return false;
        if (PRIMITIVE_TYPES.has(typeName.toLowerCase())) return false;
        if (UNITY_TYPES.has(typeName)) return false;
        if (COLLECTION_TYPES.has(typeName)) return false;
        if (SYSTEM_TYPES.has(typeName)) return false;
        if (typeName[0] !== typeName[0].toUpperCase()) return false;
        return true;
    }

    // ============================================================
    // Tag 분류
    // ============================================================

    // Tag classification for a single method
    classifyMethodTag(methodName) {
        // Skip Unity lifecycle and common methods
        if (UNITY_LIFECYCLE.has(methodName) || COMMON_METHODS.has(methodName)) {
            return { majorTag: null, minorTag: null };
        }

        let majorTag = null;
        let minorTag = null;

        for (const [tag, patterns] of Object.entries(MAJOR_TAG_PATTERNS)) {
            if (patterns.some(p => p.test(methodName))) {
                majorTag = tag;
                break;
            }
        }

        for (const [tag, patterns] of Object.entries(MINOR_TAG_PATTERNS)) {
            if (patterns.some(p => p.test(methodName))) {
                minorTag = tag;
                break;
            }
        }

        return { majorTag, minorTag };
    }

    // Aggregate tags for a class from its methods
    classifyClassTags(methods) {
        const majorCounts = {};
        const minorCounts = {};

        for (const method of methods) {
            const { majorTag, minorTag } = this.classifyMethodTag(method.methodName);
            if (majorTag) majorCounts[majorTag] = (majorCounts[majorTag] || 0) + 1;
            if (minorTag) minorCounts[minorTag] = (minorCounts[minorTag] || 0) + 1;
        }

        // Top tags by frequency
        const majorTags = Object.entries(majorCounts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(([tag]) => tag);

        const minorTags = Object.entries(minorCounts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(([tag]) => tag);

        return { major: majorTags, minor: minorTags };
    }

    // ============================================================
    // 개선된 Role 분류 (다단계)
    // ============================================================

    determineRoleAdvanced(fileId, classInfo) {
        if (!classInfo) return 'Component';

        // 우선순위 1: 타입 기반
        if (classInfo.classType === 'interface') return 'Interface';
        if (classInfo.classType === 'enum') return 'Enum';
        if (classInfo.classType === 'struct' && /Msg$|Message$/.test(classInfo.className)) return 'Message';
        if (classInfo.isAbstract) return 'Base';

        // 우선순위 2: 상속 기반
        if (classInfo.baseClass) {
            const baseName = classInfo.baseClass.split('<')[0].trim();
            for (const [role, patterns] of Object.entries(ROLE_BASE_CLASS)) {
                for (const pattern of patterns) {
                    if (baseName.includes(pattern)) {
                        return role;
                    }
                }
            }
        }

        // 우선순위 3: 인터페이스 기반
        for (const iface of classInfo.interfaces) {
            const ifaceName = iface.split('<')[0].trim();
            for (const [role, patterns] of Object.entries(ROLE_INTERFACE)) {
                for (const pattern of patterns) {
                    if (ifaceName.includes(pattern)) {
                        return role;
                    }
                }
            }
        }

        // 우선순위 4: 내용 기반
        // 모든 필드가 const/static이면 Config
        if (classInfo.fields.length > 0) {
            const allConst = classInfo.fields.every(f => f.isConst || f.isStatic);
            if (allConst && classInfo.fields.length >= 3) {
                return 'Config';
            }
        }

        // public 필드가 메서드보다 많으면 Model
        const publicFields = classInfo.fields.filter(f => f.accessModifier === 'public').length;
        const publicMethods = classInfo.methods.filter(m => m.accessModifier === 'public').length;
        if (publicFields > publicMethods && publicFields >= 3) {
            return 'Model';
        }

        // 우선순위 5: 파일명 패턴
        for (const [role, patterns] of Object.entries(ROLE_NAME_PATTERNS)) {
            for (const pattern of patterns) {
                if (pattern.test(fileId) || pattern.test(classInfo.className)) {
                    return role;
                }
            }
        }

        return 'Component';
    }

    // ============================================================
    // 개선된 Layer 분류
    // ============================================================

    determineLayerAdvanced(fileId, filePath, classInfo) {
        const pathLower = filePath.toLowerCase();
        const fileLower = fileId.toLowerCase();
        const combined = fileLower + ' ' + pathLower;

        // Domain 강제 키워드 체크 (Core보다 우선)
        for (const keyword of DOMAIN_FORCE_KEYWORDS) {
            if (combined.includes(keyword.toLowerCase())) {
                // Manager가 아닌 경우에만 Domain
                // BattleManager 같은 건 Domain으로
                return 'Domain';
            }
        }

        // Game 키워드 체크 (UI 관련)
        for (const keyword of LAYER_KEYWORDS['Game']) {
            if (fileLower.includes(keyword.toLowerCase())) {
                return 'Game';
            }
        }

        // 상속 기반 Game 체크
        if (classInfo && classInfo.baseClass) {
            const base = classInfo.baseClass.toLowerCase();
            if (['page', 'popup', 'win', 'panel', 'uibase', 'windowbase'].some(kw => base.includes(kw))) {
                return 'Game';
            }
        }

        // Core 키워드 체크
        for (const keyword of LAYER_KEYWORDS['Core']) {
            if (fileLower.includes(keyword.toLowerCase()) || pathLower.includes(keyword.toLowerCase())) {
                return 'Core';
            }
        }

        // Singleton 상속은 Core
        if (classInfo && classInfo.baseClass) {
            const base = classInfo.baseClass.toLowerCase();
            if (base.includes('singleton')) {
                return 'Core';
            }
        }

        return 'Domain';
    }

    determineGenre(fileId, filePath, content, layer) {
        const combined = (fileId + ' ' + filePath + ' ' + content.slice(0, 1000)).toLowerCase();

        const scores = {};
        for (const [genre, keywords] of Object.entries(GENRE_KEYWORDS)) {
            const score = keywords.filter(kw => combined.includes(kw.toLowerCase())).length;
            if (score > 0) {
                scores[genre] = score;
            }
        }

        if (Object.keys(scores).length > 0) {
            const detected = Object.entries(scores).sort((a, b) => b[1] - a[1])[0][0];
            return detected.charAt(0).toUpperCase() + detected.slice(1).toLowerCase();
        }

        // Core layer with no genre keywords → Generic
        if (layer === 'Core') {
            return 'Generic';
        }

        return this.defaultGenre.charAt(0).toUpperCase() + this.defaultGenre.slice(1).toLowerCase();
    }

    determineSystem(filePath, fileId) {
        const parts = filePath.split(/[/\\]/);
        const skip = new Set(['Scripts', 'Assets', 'Project', 'PPM', 'IdleMoney']);

        for (const part of parts) {
            if (!skip.has(part) && !part.endsWith('.cs')) {
                return part;
            }
        }

        return fileId;
    }
}

// ============================================================
// Database Manager
// ============================================================

class DatabaseManager {
    constructor(dbPath) {
        this.dbPath = dbPath;
        this.indices = {};
        this.loadExistingIndices();
    }

    loadExistingIndices() {
        const basePath = path.join(this.dbPath, 'base');
        if (!fs.existsSync(basePath)) return;

        for (const genre of fs.readdirSync(basePath)) {
            const genrePath = path.join(basePath, genre);
            if (!fs.statSync(genrePath).isDirectory()) continue;

            for (const layer of fs.readdirSync(genrePath)) {
                const layerPath = path.join(genrePath, layer);
                if (!fs.statSync(layerPath).isDirectory()) continue;

                const indexPath = path.join(layerPath, 'index.json');
                if (fs.existsSync(indexPath)) {
                    const key = `${genre}_${layer}`;
                    try {
                        this.indices[key] = JSON.parse(fs.readFileSync(indexPath, 'utf-8'));
                    } catch (e) {
                        this.indices[key] = [];
                    }
                }
            }
        }
    }

    addFile(fileInfo) {
        const genre = fileInfo.genre.toLowerCase();
        const layer = fileInfo.layer.toLowerCase();

        const genrePath = path.join(this.dbPath, 'base', genre, layer);
        const filesPath = path.join(genrePath, 'files');

        if (!fs.existsSync(filesPath)) {
            fs.mkdirSync(filesPath, { recursive: true });
        }

        const filePath = path.join(filesPath, `${fileInfo.fileId}.json`);
        fs.writeFileSync(filePath, JSON.stringify(fileInfo, null, 2), 'utf-8');

        const key = `${genre}_${layer}`;
        if (!this.indices[key]) {
            this.indices[key] = [];
        }

        this.indices[key] = this.indices[key].filter(e => e.fileId !== fileInfo.fileId);

        this.indices[key].push({
            fileId: fileInfo.fileId,
            layer: fileInfo.layer,
            genre: fileInfo.genre,
            role: fileInfo.role,
            system: fileInfo.system,
            score: fileInfo.score,
            provides: fileInfo.provides.slice(0, 5),
            requires: fileInfo.requires.slice(0, 5),
            tags: fileInfo.tags
        });
    }

    saveIndices() {
        for (const [key, entries] of Object.entries(this.indices)) {
            const [genre, layer] = key.split('_');
            const indexPath = path.join(this.dbPath, 'base', genre, layer, 'index.json');

            const dir = path.dirname(indexPath);
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true });
            }

            fs.writeFileSync(indexPath, JSON.stringify(entries, null, 2), 'utf-8');
        }
    }
}

// ============================================================
// File Walker
// ============================================================

function* walkDir(dir) {
    const files = fs.readdirSync(dir);
    for (const file of files) {
        const filePath = path.join(dir, file);
        const stat = fs.statSync(filePath);
        if (stat.isDirectory()) {
            yield* walkDir(filePath);
        } else {
            yield filePath;
        }
    }
}

// ============================================================
// Main
// ============================================================

function parseProject(sourcePath, genre, dbPath) {
    const parser = new CSharpParser(genre);
    const db = new DatabaseManager(dbPath);

    const stats = {
        total: 0,
        parsed: 0,
        failed: 0,
        byLayer: {},
        byGenre: {},
        byRole: {},
        byMajorTag: {}
    };

    console.log(`\nParsing: ${sourcePath}`);
    console.log(`Default Genre: ${genre}`);
    console.log('-'.repeat(50));

    for (const filePath of walkDir(sourcePath)) {
        if (!filePath.endsWith('.cs')) continue;

        const relative = path.relative(sourcePath, filePath);

        if (['Editor', 'Test', 'Plugins', 'ThirdParty'].some(skip => relative.includes(skip))) {
            continue;
        }

        stats.total++;

        const fileInfo = parser.parseFile(filePath, relative);

        if (fileInfo) {
            db.addFile(fileInfo);
            stats.parsed++;

            stats.byLayer[fileInfo.layer] = (stats.byLayer[fileInfo.layer] || 0) + 1;
            stats.byGenre[fileInfo.genre] = (stats.byGenre[fileInfo.genre] || 0) + 1;
            stats.byRole[fileInfo.role] = (stats.byRole[fileInfo.role] || 0) + 1;

            if (fileInfo.tags) {
                for (const tag of fileInfo.tags.major) {
                    stats.byMajorTag[tag] = (stats.byMajorTag[tag] || 0) + 1;
                }
            }

            if (stats.parsed % 100 === 0) {
                console.log(`  Parsed: ${stats.parsed} files...`);
            }
        } else {
            stats.failed++;
        }
    }

    db.saveIndices();

    console.log('-'.repeat(50));
    console.log(`Total: ${stats.total}`);
    console.log(`Parsed: ${stats.parsed}`);
    console.log(`Failed: ${stats.failed}`);
    console.log(`\nBy Layer:`, stats.byLayer);
    console.log(`By Genre:`, stats.byGenre);

    const topRoles = Object.entries(stats.byRole)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 15)
        .reduce((obj, [k, v]) => { obj[k] = v; return obj; }, {});
    console.log(`By Role (top 15):`, topRoles);
    console.log(`By Major Tag:`, stats.byMajorTag);

    return stats;
}

// CLI
const args = process.argv.slice(2);
if (args.length < 2) {
    console.log('Usage: node parser.js <source_path> <genre> [db_path]');
    console.log('  genre: RPG, Idle, Merge, SLG, Tycoon, Simulation, Puzzle, Generic');
    process.exit(1);
}

const sourcePath = args[0];
const genre = args[1].toUpperCase();
const dbPath = args[2] || 'E:/AI/db';

parseProject(sourcePath, genre, dbPath);
