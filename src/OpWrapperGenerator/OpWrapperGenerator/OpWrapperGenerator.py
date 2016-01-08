from ctypes import *
import logging

class EnumType:
    name = ''
    enumValues = []
    def __init__(self, typeName = 'ElementWiseOpType', \
                 typeString = "{'avg', 'max', 'sum'}"):
        self.name = typeName
        if (typeString[0] == '{'):  # is a enum type
            isEnum = True
            # parse enum
            self.enumValues = typeString[typeString.find('{') + 1:typeString.find('}')].split(',')
            for i in range(0, len(self.enumValues)):
                self.enumValues[i] = self.enumValues[i].strip().strip("'")
        else:
            logging.warn("trying to parse none-enum type as enum: %s" % typeString)
    def GetDefinitionString(self, indent = 0):
        indentStr = ' ' * indent
        ret = indentStr + 'enum %s {\n' % self.name
        for i in range(0, len(self.enumValues)):
            ret = ret + indentStr + '  %s = %d' % (self.enumValues[i], i)
            if (i != len(self.enumValues) -1):
                ret = ret + ","
            ret = ret + "\n"
        ret = ret + "};\n"
        return ret
    def GetDefaultValueString(self, value = ''):
        return self.name + "::" + value
    def GetEnumStringArray(self, indent = 0):
        indentStr = ' ' * indent
        ret = indentStr + 'static const char *%sValues[] = {\n' % self.name
        for i in range(0, len(self.enumValues)):
            ret = ret + indentStr + '  "%s"' % self.enumValues[i]
            if (i != len(self.enumValues) -1):
                ret = ret + ","
            ret = ret + "\n"
        ret = ret + indentStr + "};\n"
        return ret
    def GetConvertEnumVariableToString(self, variable=''):
        return "%sValues[int(%s)]" % (self.name, variable)

class Arg:
    typeDict = {'boolean':'bool',\
        'Shape(tuple)':'Shape',\
        'Symbol':'Symbol',\
        'float':'mx_float',\
        'int':'int',\
        'long':'int64_t'}
    name = ''
    type = ''
    description = ''
    isEnum = False
    enum = None
    hasDefault = False
    defaultString = ''
    def __init__(self, opName = '', argName = '', typeString = '', descString = ''):
        self.name = argName
        self.description = descString
        if (typeString[0] == '{'):  # is enum type
            self.isEnum = True
            self.enum = EnumType(self.ConstructEnumTypeName(opName, argName), typeString)
            self.type = self.enum.name
        else:
            try:
                self.type = self.typeDict[typeString.split()[0].strip(',')]
            except:
                pass
        if typeString.find('default=') != -1:
            self.hasDefault = True
            self.defaultString = typeString.split('default=')[1].strip().strip("'")
            if self.isEnum:
                self.defaultString = self.enum.GetDefaultValueString(self.defaultString)
    def ConstructEnumTypeName(self, opName = '', argName = ''):
        a = opName[0].upper()
        # format ArgName so instead of act_type it returns ActType
        argNameWords = argName.split('_')
        argName = ''
        for an in argNameWords:
            argName = argName + an[0].upper() + an[1:]
        typeName = a + opName[1:] + argName
        return typeName

class Op:
    name = ''
    description = ''
    args = []

    def __init__(self, name = '', description = '', args = []):
        self.name = name
        self.description = description
        # reorder arguments, put those with default value to the end
        orderedArgs = []
        for arg in args:
            if not arg.hasDefault:
                orderedArgs.append(arg)
        for arg in args:
            if arg.hasDefault:
                orderedArgs.append(arg)
        self.args = orderedArgs
    def GetOpDefinitionString(self, indent=0):
        ret = ''
        indentStr = ' ' * indent
        # define enums if any
        for arg in self.args:
            if arg.isEnum:
                # comments
                pattern = ("/*! \\brief %s*/\n")
                ret = ret + indentStr + (pattern % arg.description)
                # definition
                ret = ret + arg.enum.GetDefinitionString(indent) + '\n'
        # create function comments
        pattern = ("/*!\n"
                   " * \\brief %s\n")
        ret = ret + pattern % self.description
        for arg in self.args:
            line = " * \\param %s %s\n" % (arg.name, arg.description)
            ret = ret + line
        ret = ret + " * \\return new symbol\n"
        ret = ret + " */\n"
        # create function header
        declFirstLine = indentStr + 'Symbol %s(' % self.name
        ret = ret + declFirstLine
        argIndentStr = ' ' * len(declFirstLine)
        if len(self.args) != 0:
            ret = ret + self.GetArgString(self.args[0])
        for i in range(1, len(self.args)):
            ret = ret + ',\n'
            ret = ret + argIndentStr + self.GetArgString(self.args[i])
        ret = ret + ') {\n'
        # create function body
        # if there is enum, generate static enum<->string mapping
        for arg in self.args:
            if arg.isEnum:
                ret = ret + arg.enum.GetEnumStringArray(indent + 2)
        # now generate code
        ret = ret + indentStr + '  return Operator(\"%s\")\n' % self.name
        for arg in self.args:
            v = arg.name
            if arg.isEnum:
                v = arg.enum.GetConvertEnumVariableToString(v)
            ret = ret + indentStr + ' ' * 11 + \
                '.SetParam(\"%s\", %s)\n' % (arg.name, v)
        ret = ret + indentStr + '}\n'
        return ret
    def GetArgString(self, arg):
        ret = '%s %s' % (arg.type, arg.name)
        if arg.hasDefault:
            ret = ret + ' = ' + arg.defaultString
        return ret

def ParseAllOps():
    """
    MXNET_DLL int MXSymbolListAtomicSymbolCreators(mx_uint *out_size,
                                                   AtomicSymbolCreator **out_array);

    MXNET_DLL int MXSymbolGetAtomicSymbolInfo(AtomicSymbolCreator creator,
                                              const char **name,
                                              const char **description,
                                              mx_uint *num_args,
                                              const char ***arg_names,
                                              const char ***arg_type_infos,
                                              const char ***arg_descriptions,
                                              const char **key_var_num_args);
    """
    ListOP = cdll.libmxnet.MXSymbolListAtomicSymbolCreators
    GetOpInfo = cdll.libmxnet.MXSymbolGetAtomicSymbolInfo
    ListOP.argtypes=[POINTER(c_int), POINTER(POINTER(c_void_p))]
    GetOpInfo.argtypes=[c_void_p, \
        POINTER(c_char_p), \
        POINTER(c_char_p), \
        POINTER(c_int), \
        POINTER(POINTER(c_char_p)), \
        POINTER(POINTER(c_char_p)), \
        POINTER(POINTER(c_char_p)), \
        POINTER(c_char_p)]

    nOps = c_int()
    opHandlers = POINTER(c_void_p)()
    r = ListOP(byref(nOps), byref(opHandlers))
    ret = ''
    for i in range(0, nOps.value):
        handler = opHandlers[i]
        name = c_char_p()
        description = c_char_p()
        nArgs = c_int()
        argNames = POINTER(c_char_p)()
        argTypes = POINTER(c_char_p)()
        argDescs = POINTER(c_char_p)()
        varArgName = c_char_p()
        GetOpInfo(handler, byref(name), byref(description), \
            byref(nArgs), byref(argNames), byref(argTypes), \
            byref(argDescs), byref(varArgName))
        if name.value.decode()[0]=='_':     # get rid of functions like __init__
            continue
        args = []
        for i in range(0, nArgs.value):
            arg = Arg(name.value.decode(),
                      argNames[i].decode(),
                      argTypes[i].decode(),
                      argDescs[i].decode())
            args.append(arg)
        op = Op(name.value.decode(), description.value.decode(), args)
        ret = ret + op.GetOpDefinitionString() + "\n"
    return ret

if __name__ == "__main__":
    #et = EnumType(typeName = 'MyET')
    #print(et.GetDefinitionString())
    #print(et.GetEnumStringArray())
    #arg = Arg()
    #print(arg.ConstructEnumTypeName('SoftmaxActivation', 'act_type'))
    #arg = Arg(opName = 'FullConnected', argName='act_type', \
    #    typeString="{'elu', 'leaky', 'prelu', 'rrelu'},optional, default='leaky'", \
    #    descString='Activation function to be applied.')
    #print(arg.isEnum)
    #print(arg.defaultString)
    #arg = Arg("fc", "alpha", "float, optional, default=0.0001", "alpha")
    #decl = "%s %s" % (arg.type, arg.name)
    #if arg.hasDefault:
    #    decl = decl + "=" + arg.defaultString
    #print(decl)

    # generate file header
    patternStr = ("#ifndef _MXNETOP_H\n"
                 "#define _MXNETOP_H\n"
                 "\n"
                 "#include \"MxNetCpp.h\""
                 "\n"
                 "namespace mxnet {\n"
                 "namespace cpp {\n"
                 "\n"
                 "%s"
                 "} //namespace cpp\n"
                 "} //namespace mxnet\n")
    with open('../../../include/MxNetOp.h', 'w') as f:
        f.write(patternStr % ParseAllOps())
    pass