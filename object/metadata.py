from asyncio import exceptions
from datetime import datetime
from selectors import SelectorKey
from typing import Iterator
from xml.dom.pulldom import ErrorHandler
import win32com.client as w32
import pandas as pd
import re
import numpy as np
from object.enumerations import objectTypeConstants, dataTypeConstants

import collections.abc
#hyper needs the four following aliases to be done manually.
collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping
collections.MutableSet = collections.abc.MutableSet
collections.MutableMapping = collections.abc.MutableMapping

import savReaderWriter

class mrDataFileDsc:
    def __init__(self, **kwargs):
        self.mdd_file = kwargs.get("mdd_file") if "mdd_file" in kwargs.keys() else None
        self.ddf_file = kwargs.get("ddf_file") if "ddf_file" in kwargs.keys() else None
        self.dms_file = kwargs.get("dms_file") if "dms_file" in kwargs.keys() else None
        self.cleandata_dms_file = kwargs.get("cleandata_file") if "cleandata_file" in kwargs.keys() else None
        self.sql_query = kwargs.get("sql_query") if "sql_query" in kwargs.keys() else None
        self.default_language = kwargs.get("default_language") if "default_language" in kwargs.keys() else None 
        
        self.MDM = w32.Dispatch(r'MDM.Document')
        self.adoConn = w32.Dispatch(r'ADODB.Connection')
        self.adoRS = w32.Dispatch(r'ADODB.Recordset')
        self.DMOMJob = w32.Dispatch(r'DMOM.Job')
        self.Directives = w32.Dispatch(r'DMOM.StringCollection')

    def openMDM(self):
        self.MDM.Open(self.mdd_file)
        if self.default_language is not None: self.MDM.Languages.Base = self.default_language

    def saveMDM(self):
        self.MDM.Save(self.mdd_file)

    def closeMDM(self):
        self.MDM.Close()

    def openDataSource(self):
        conn = "Provider=mrOleDB.Provider.2; Data Source = mrDataFileDsc; Location={}; Initial Catalog={}; Mode=ReadWrite; MR Init Category Names=1".format(self.ddf_file, self.mdd_file)

        self.adoConn.Open(conn)

        self.adoRS.ActiveConnection = conn
        self.adoRS.Open(self.sql_query)
        
    def closeDataSource(self):
        #Close and clean up
        if self.adoRS.State == 1:
            self.adoRS.Close()
            self.adoRS = None
        if self.adoConn is not None:
            self.adoConn.Close()
            self.adoConn = None

    def runDMS(self):
        try:
            self.Directives.Clear()
            self.Directives.add('#define InputDataFile ".\{}"'.format(self.mdd_file))

            self.Directives.add('#define OutputDataMDD ".\{}"'.format(self.mdd_file.replace('.mdd', '_EXPORT.mdd')))
            self.Directives.add('#define OutputDataDDF ".\{}"'.format(self.mdd_file.replace('.mdd', '_EXPORT.ddf')))

            self.DMOMJob.Load(self.dms_file, self.Directives)
            self.DMOMJob.Run()
        except Exception as ex:
            print(ex.args)

    def runCleanDataDMS(self, mode=''):
        try:
            self.Directives.Clear()
            self.Directives.add('#define InputDataDDF ".\{}"'.format(self.ddf_file))
            self.Directives.add('#define InputDataMDD ".\{}"'.format(self.mdd_file))
            
            if mode == 'CE':
                self.Directives.add('#define OutputDataDDF ".\{}"'.format(self.ddf_file.replace('_EXPORT.ddf', '_CE.ddf')))
                self.Directives.add('#define OutputDataMDD ".\{}"'.format(self.mdd_file.replace('_EXPORT.mdd', '_CE.mdd')))
            elif mode == 'OE':  
                self.Directives.add('#define OutputDataDDF ".\{}"'.format(self.ddf_file.replace('_CE.ddf', '_OE.ddf')))
                self.Directives.add('#define OutputDataMDD ".\{}"'.format(self.mdd_file.replace('_CE.mdd', '_OE.mdd')))

            self.Directives.add('#define SelectQueryString "{}"'.format(self.sql_query))

            self.DMOMJob.Load(self.dms_file, self.Directives)
            

            # self.DMOMJob.Log.LogInfo("Python: bắt đầu chạy job")
            self.DMOMJob.Run()
            # self.DMOMJob.Log.LogInfo("Python: kết thúc job")

            print("Job log:", self.DMOMJob.Log)
            
            private_log = self.DMOMJob.Log.CreatePrivateLog()
            self.DMOMJob.PublishLogs = True
            self.DMOMJob.Log = private_log
        except Exception as ex:
            print(ex.args)

class Metadata(mrDataFileDsc):
    def __init__(self, **kwargs):
        try:
            self.mdd_file = kwargs.get("mdd_file") if "mdd_file" in kwargs.keys() else None
            self.ddf_file = kwargs.get("ddf_file") if "ddf_file" in kwargs.keys() else None
            self.dms_file = kwargs.get("dms_file") if "dms_file" in kwargs.keys() else None
            self.sql_query = kwargs.get("sql_query") if "sql_query" in kwargs.keys() else None
            self.default_language = kwargs.get("default_language") if "default_language" in kwargs.keys() else None 

            mrDataFileDsc.__init__(self, mdd_file=self.mdd_file, ddf_file=self.ddf_file, dms_file=self.dms_file, sql_query=self.sql_query)

        except ValueError as ex:
            print("Error")
    
    def handle_defined_list(self, question_name, syntax):
        if self.MDM.Types.Exist(question_name):
            self.MDM.Types.Remove(question_name)

        self.MDM.Types.addScript(syntax)

    def handle_nested_fields(self, question_name, syntax, field_parent, parent_nodes):
        if parent_nodes:
            field = self.get_nested_field(parent_nodes)

            if field and field.Fields.Exist(question_name):
                field.Fields.Remove(question_name)
            
            field.Fields.addScript(syntax)
        else:
            target_field = self.MDM.Fields if field_parent is None else field_parent.Fields

            if target_field.Exist(question_name):
                target_field.Remove(question_name)
            
            target_field.addScript(syntax)

    def get_nested_field(self, parent_nodes, field_parent=None):
        """Recursively retrieves the nested field based on parent nodes."""
        if len(parent_nodes) == 1:
            return self.MDM.Fields[parent_nodes[0]] if field_parent is None else field_parent.Fields[parent_nodes[0]]
        else:
            return self.get_nested_field(parent_nodes[1:], field_parent=self.MDM.Fields[parent_nodes[0]] if field_parent is None else field_parent.Fields[parent_nodes[0]])

    def addScript(self, question_name, syntax, field_parent=None, is_defined_list=False, parent_nodes=list(), globalization=None):
        try:
            self.openMDM()

            if question_name in ['_LIST_TOUCHPOINT_QV1a']:
                a = ""

            if is_defined_list:
                self.handle_defined_list(question_name, syntax)
            else:
                self.handle_nested_fields(question_name, syntax, field_parent, parent_nodes)
            
            if globalization is not None:
                if len([l for l in ['vi','en'] if l in globalization.languages]) >= 1:
                    self.translate(question_name, is_defined_list=is_defined_list, parent_nodes=parent_nodes, globalization=globalization)

        except Exception as ex:
            print(",".join(ex.args))
        finally:
            self.saveMDM()
            self.closeMDM()
    
    def handle_translate_defined_list(self, question_name, globalization=dict()):
        current_language = 'vi'

        if len(globalization.languages) == 1:
            current_language = globalization.languages[0]

        if question_name in globalization.keys():
            self.MDM.Types[question_name].Labels.Text = globalization[question_name][current_language]

        for element in self.MDM.Types[question_name].Elements:
            if f"{question_name}.{element.Name}" in globalization.keys():
                element.Labels.Text = globalization[f"{question_name}.{element.Name}"][current_language]

    def handle_translate_question(self, field, globalization=dict()):
        current_language = 'vi'

        if len(globalization.languages) == 1:
            current_language = globalization.languages[0]

        question_fullname = re.sub(pattern='\.\.', repl='', string=field.FullName)

        if question_fullname in ['P_NAT_2']:
            a = ""

        match str(field.ObjectTypeValue):
            case objectTypeConstants.mtVariable.value:
                if field.DataType == dataTypeConstants.mtCategorical.value:
                    if question_fullname in globalization.keys():    
                        field.Labels.Text = globalization[question_fullname][current_language]

                    for category in field.Categories:
                        if f"{question_fullname}.{category.Name}" in globalization.keys():
                            category.Labels.Text = globalization[f"{question_fullname}.{category.Name}"][current_language]

                else:
                    if question_fullname in globalization.keys():
                        field.Labels.Text = globalization[question_fullname][current_language]
            case objectTypeConstants.mtClass.value: #Block Fields
                if question_fullname in globalization.keys():  
                    field.Labels.Text = globalization[question_fullname][current_language]
            case objectTypeConstants.mtArray.value: #Loop
                if question_fullname in globalization.keys():  
                    field.Labels.Text = globalization[question_fullname][current_language]

                for category in field.Categories:
                    if f"{field.Name}.{category.Name}" in globalization.keys():
                        category.Labels.Text = globalization[f"{field.Name}.{category.Name}"][current_language]

    def translate(self, question_name, is_defined_list=False, parent_nodes=list(), globalization=dict()):
        try:
            self.MDM.Languages.Current = "ENU"

            if question_name in ['_LST_WARDS']:
                a = ""

            field_parent = None

            if is_defined_list:
                self.handle_translate_defined_list(question_name, globalization)
            else:
                if parent_nodes:
                    field_parent = self.get_nested_field(parent_nodes)
                
                field = self.MDM.Fields[question_name] if field_parent is None else field_parent.Fields[question_name]
                
                self.handle_translate_question(field, globalization)

        except Exception as ex:
            print(ex.args)
        finally:
            self.MDM.Languages.Current = "VIT"
        
    def getVariables(self):
        self.openMDM()
        arr = list()
        for v in self.MDM.Variables:
            arr.append(v.FullName)
        self.closeMDM()
        return arr

    def addField(self, field):
        self.openMDM()
        self.MDM.Fields.Add(field)
        self.closeMDM()
    
    def getField(self, name):
        self.openMDM()
        field = self.MDM.Fields[name]
        self.closeMDM()
        return field
    
    def convertToDataFrame(self, questions):
        self.openMDM()
        self.openDataSource()
        
        d = { 'columns' : list(), 'values' : list() }

        i = 0
        
        while not self.adoRS.EOF:
            r = self.getRows(questions, i)

            d['values'].append(r['values'])
            
            if i == 0: 
                d['columns'].append(r['columns'])

            i += 1
            self.adoRS.MoveNext()

        self.closeMDM()
        self.closeDataSource()
        
        if len(d['values']) > 0:
            return pd.DataFrame(data=d['values'], columns=d['columns'][0])
        else:
            return pd.DataFrame()
        
    def getRows(self, questions, row_index):
        r = {
            'columns' : list(),
            'values' : list()  
        }

        for question in questions:
            q = self.getRow(self.MDM.Fields[question], row_index)

            r['values'].extend(q['values'])
            r['columns'].extend(q['columns'])

        return r

    def getRow(self, field, row_index):
        r = {
            'columns' : list(),
            'values' : list()  
        }

        match str(field.ObjectTypeValue):
            case objectTypeConstants.mtVariable.value:
                q = self.getValue(field)
                        
                r['values'].extend(q['values'])
                r['columns'].extend(q['columns'])
            case objectTypeConstants.mtRoutingItems.value:
                if field.UsageType != 1048:
                    q = self.getValue(field)
                    
                    r['values'].extend(q['values'])
                    r['columns'].extend(q['columns'])
            case objectTypeConstants.mtClass.value: #Block Fields
                for f in field.Fields:
                    if f.Properties["py_isHidden"] is None or f.Properties["py_isHidden"] == False:
                        q = self.getRow(f, row_index)
                        
                        r['values'].extend(q['values'])
                        r['columns'].extend(q['columns'])
            case objectTypeConstants.mtArray.value: #Loop
                a = field.Name

                for variable in field.Variables:
                    if variable.Properties["py_isHidden"] is None or variable.Properties["py_isHidden"] == False:
                        q = self.getRow(variable, row_index)
                        
                        r['values'].extend(q['values'])
                        r['columns'].extend(q['columns'])
        return r

    def getValue(self, question): 
        q = {
            'columns' : list(),
            'values' : list()  
        }
        
        max_range = 0
        
        column_name = question.FullName if str(question.ObjectTypeValue) != objectTypeConstants.mtVariable.value else question.Variables[0].FullName

        if str(question.ObjectTypeValue) == objectTypeConstants.mtRoutingItems.value:
            if question.Properties["py_setColumnName"] is not None:
                s = ""

                for i in range(question.Indices.Count):
                    s = s + question.Indices[i].FullName.replace("_","_R")
                    
                alias_name = "{}{}".format(question.Properties["py_setColumnName"], s)
                #alias_name = "{}{}".format(question.Properties["py_setColumnName"], question.Indices[0].FullName.replace("_","_R"))
            else:
                alias_name = column_name
        else:
            if question.LevelDepth == 1:
                if question.UsageTypeName == "OtherSpecify":
                    alias_name = "{}{}".format(column_name if question.Parent.Properties["py_setColumnName"] is None else question.Parent.Properties["py_setColumnName"], question.Name)
                else:
                    alias_name = column_name if question.Properties["py_setColumnName"] is None else question.Properties["py_setColumnName"]
            elif question.LevelDepth == 2:
                current_index_path = re.sub(pattern="{Recall_|}", repl="", string=question.CurrentIndexPath) 

                if question.UsageTypeName == "OtherSpecify":
                    alias_name = "{}{}".format(column_name if question.Parent.Properties["py_setColumnName"] is None else question.Parent.Properties["py_setColumnName"], question.Name)
                else:
                    alias_name = column_name if question.Properties["py_setColumnName"] is None else question.Properties["py_setColumnName"]

                alias_name = "p{}_{}".format(current_index_path, alias_name)

        if question.DataType == dataTypeConstants.mtCategorical.value:    
            show_helperfields = False if question.Properties["py_showHelperFields"] is False else True

            cats_resp = str(self.adoRS.Fields[column_name].Value)[1:(len(str(self.adoRS.Fields[column_name].Value))-1)].split(",")

            if question.Properties["py_showPunchingData"]:
                for category in question.Categories:
                    if not category.IsOtherLocal:
                        q['columns'].append("{}{}".format(alias_name, category.Name.replace("_", "_C")))
                        
                        if question.Properties["py_showVariableValues"] is None:
                            if category.Name in cats_resp:
                                q['values'].append(1)
                            else:
                                q['values'].append(0 if self.adoRS.Fields[column_name].Value is not None else np.nan)
                        else:
                            if category.Name in cats_resp:
                                q['values'].append(category.Label) 
                            else:
                                q['values'].append(np.nan)
                
                if question.HelperFields.Count > 0:
                    if question.Properties["py_combibeHelperFields"]:
                        q['columns'].append("{}{}".format(alias_name, category.Name.replace(category.Name, "_C97")))
                            
                        str_others = ""

                        for helperfield in question.HelperFields:
                            if helperfield.Name in cats_resp:
                                str_others = str_others + (", " if len(str_others) > 0 else "") + self.adoRS.Fields["{}.{}".format(column_name, helperfield.Name)].Value
                        
                        if len(str_others) > 0:
                            match question.Properties["py_showVariableValues"]:
                                case "Names":
                                    q['values'].append(question.Categories[helperfield.Name].Name.replace('_',''))
                                case "Labels":
                                    q['values'].append(question.Categories[helperfield.Name].Label)
                                case _:
                                    q['values'].append(1)
                        else:
                            q['values'].append(np.nan)
                        
                        if show_helperfields:
                            q['columns'].append("{}{}".format(alias_name, category.Name.replace(category.Name, "_C97_Other")))

                            if len(str_others) > 0:
                                q['values'].append(str_others) 
                            else:
                                q['values'].append(np.nan)
                    else:
                        for helperfield in question.HelperFields:
                            q['columns'].append("{}{}".format(alias_name, helperfield.Name.replace("_", "_C")))
                            
                            if question.Properties["py_showVariableValues"] is None:
                                if helperfield.Name in cats_resp:
                                    q['values'].append(1)
                                else:
                                    q['values'].append(0 if self.adoRS.Fields[column_name].Value is not None else np.nan)
                            else:
                                if helperfield.Name in cats_resp:
                                    q['values'].append(helperfield.Label) 
                                else:
                                    q['values'].append(np.nan)

                            if show_helperfields:
                                q['columns'].append("{}{}_Other".format(alias_name, helperfield.Name.replace("_", "_C")))

                                if helperfield.Name in cats_resp:
                                    q['values'].append(self.adoRS.Fields["{}.{}".format(column_name, helperfield.Name)].Value)
                                else: 
                                    q['values'].append(np.nan)
            elif question.Properties["py_showVariableValues"] == "Names":
                q['columns'].append(alias_name)
                q['values'].append(np.nan if self.adoRS.Fields[column_name].Value == None else self.adoRS.Fields[column_name].Value)
            else:
                max_range = question.MaxValue if question.MaxValue is not None else question.Categories.Count
                
                for i in range(max_range):
                    col_name = alias_name if question.MinValue == 1 and question.MaxValue == 1 else "{}_{}".format(alias_name, i + 1)
                    q['columns'].append(col_name)

                    #Generate a column which contain a factor of a category variable (only for single answer question)
                    if question.MinValue == 1 and question.MaxValue == 1:
                        if question.Properties["py_showVariableFactor"] is not None:
                            col_name = "FactorOf{}".format(alias_name)
                            q['columns'].append(col_name)

                    if i < len(cats_resp):
                        category = cats_resp[i]

                        match question.Properties["py_showVariableValues"]:
                            case "Names":
                                q['values'].append(np.nan if self.adoRS.Fields[column_name].Value == None else question.Categories[category].Name)
                            case "Labels":
                                q['values'].append(np.nan if self.adoRS.Fields[column_name].Value == None else question.Categories[category].Label)
                            case _:
                                if type(category[1:len(category)]) is str:
                                    q['values'].append(np.nan if self.adoRS.Fields[column_name].Value == None else str(category[1:len(category)]))
                                else:
                                    q['values'].append(np.nan if self.adoRS.Fields[column_name].Value == None else int(category[1:len(category)]))
                        
                        #Get factor value of a category variable
                        if question.MinValue == 1 and question.MaxValue == 1:
                            if question.Properties["py_showVariableFactor"] is not None:
                                q['values'].append(np.nan if self.adoRS.Fields[column_name].Value == None else question.Categories[category].Factor)
                    else:
                        q['values'].append(np.nan)

                        #Get factor value of a category variable
                        if question.MinValue == 1 and question.MaxValue == 1:
                            if question.Properties["py_showVariableFactor"] is not None:
                                q['values'].append(np.nan)
                
                if show_helperfields:
                    if question.HelperFields.Count > 0:
                        for helperfield in question.HelperFields:
                            col_name = "{}{}_Other".format(alias_name, helperfield.Name.replace("_", "_C"))
                            q['columns'].append(col_name)

                            if helperfield.Name in cats_resp:
                                q['values'].append(np.nan if self.adoRS.Fields["{}.{}".format(column_name, helperfield.Name)].Value == None else self.adoRS.Fields["{}.{}".format(column_name, helperfield.Name)].Value)
                            else:
                                q['values'].append(np.nan) 

        elif question.DataType == dataTypeConstants.mtDate.value:
            q['columns'].append(alias_name)
            q['values'].append(np.nan if self.adoRS.Fields[column_name].Value is None else datetime.strftime(self.adoRS.Fields[column_name].Value, "%d/%m/%Y"))
        elif question.DataType == dataTypeConstants.mtLong.value or question.DataType == dataTypeConstants.mtDouble.value:
            q['columns'].append(alias_name)
            q['values'].append(self.adoRS.Fields[column_name].Value)
        else:
            q['columns'].append(alias_name)
            q['values'].append('' if self.adoRS.Fields[column_name].Value is None else self.adoRS.Fields[column_name].Value)

        if len(q['columns']) != len(q['values']):
            print("A length mismatch error between 'columns': {} and 'values': {}".format(','.join(q['columns']), ','.join(q['values']))) 

        return q

    def addAxisExpressions(self, axisexpressions=list()):
        try:
            self.openMDM()
            
            for question_name, axis_expression in axisexpressions.items():
                parent_nodes = question_name.split('.')

                if len(parent_nodes) == 1:
                    field = self.MDM.Fields[parent_nodes[0]]
                else:
                    target_field = self.get_nested_field(parent_nodes=parent_nodes[0:len(parent_nodes)-1])

                    field = target_field.Fields[parent_nodes[len(parent_nodes)-1]]

                field.AxisExpression = axis_expression

        except Exception as ex:
            print(ex.args)
        finally:
            self.saveMDM()
            self.closeMDM()
    