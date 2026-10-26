from object.metadata import mrDataFileDsc
from object.enumerations import objectTypeConstants, dataTypeConstants
from datetime import datetime
import savReaderWriter
import pandas as pd
import numpy as np
import re
from tqdm import tqdm
from object.transform import Transform

class SPSSObject(mrDataFileDsc):
    def __init__(self, mdd_path, ddf_path, sql_query, questions, group_name=None):
        mrDataFileDsc.__init__(self, mdd_file=mdd_path, ddf_file=ddf_path, sql_query=sql_query)

        self.df = pd.DataFrame()
        self.df_spss = pd.DataFrame()

        self.records = list()
        self.varNames = list()
        self.varMissingValues = dict() 
        self.varLabels = dict()
        self.varTypes = dict()
        
        self.valueLabels = dict()
        self.measureLevels = dict()
        self.var_date_formats = dict()
        self.var_dates = list()

        #Group of columns with format A_suffix1, A_suffix2...B_suffix1, B_suffix2
        self.group_name = group_name
        
        self.init(questions)

    def init(self, questions):
        self.openMDM()
        self.openDataSource()
        
        data = self.adoRS.GetRows()

        columns = [f.Name for f in self.adoRS.Fields]
        
        self.df = pd.DataFrame(data=np.array(data).T, columns=columns)
        self.transform(questions)

        self.closeMDM()
        self.closeDataSource()

    def transform(self, questions):
        
        if len(questions) == 0:
            for field in self.MDM.Fields:
                if field.Properties["py_isHidden"] is None or field.Properties["py_isHidden"] == False:
                    self.generate_variable(field)
        else:
            for question in tqdm(questions, desc=f"Tranfrom data..") :
                field = self.MDM.Fields[question]

                if field.Properties["py_isHidden"] is None or field.Properties["py_isHidden"] == False:
                    self.generate_variable(field)

    def get_iterations(self, field, indexes):
        indexes = indexes.split(',')
        iterations = list()

        def findIteration(f, index):
            if index < 0:
                return
            
            if len(indexes[index]) == 0:
                return

            iterations.append(f.Categories[re.sub(pattern="[\{\}]", repl="", string=indexes[index])])
            findIteration(f.Parent.Parent, index - 1)

        findIteration(field, len(indexes) - 1)
        return iterations
        
    def generate_variable(self, field, iterations_list=list(), iterations=list()):

        if str(field.ObjectTypeValue) == objectTypeConstants.mtVariable.value:
            if field.LevelDepth > 1:
                if field.Parent.Parent.Name == "@class":
                    iterations = self.get_iterations(field.Parent.Parent.Parent, field.CurrentIndexPath) 
                else:
                    iterations = self.get_iterations(field.Parent.Parent, field.CurrentIndexPath) 

            if field.DataType in [ dataTypeConstants.mtLong.value, dataTypeConstants.mtDouble.value, dataTypeConstants.mtText.value, dataTypeConstants.mtBoolean.value ]:
                self.transform_simple_data(field, iterations=iterations)
            elif field.DataType == dataTypeConstants.mtCategorical.value:
                self.transform_categorical_data(field, iterations=iterations)
        elif str(field.ObjectTypeValue) == objectTypeConstants.mtClass.value:
            for f in field.Fields:
                if f.Properties["py_isHidden"] is None or f.Properties["py_isHidden"] == False:
                    self.generate_variable(f)
        elif str(field.ObjectTypeValue) == objectTypeConstants.mtArray.value:
            iterations_list = list()

            if field.Properties["py_setCategoriesList"]:
                iterations_list = field.Properties["py_setCategoriesList"].split(',')
            else:
                iterations_list = [cat.Name for cat in field.Categories]

            for f in field.Fields:
                if f.Properties["py_isHidden"] is None or f.Properties["py_isHidden"] == False:
                    full_name = f.FullName.replace("..","%s") % tuple(field.CurrentIndexPath.split(','))
                    for iteration in iterations_list:
                        iteration_full_name = full_name.replace("[..]", "[{%s}]" % iteration)
                        self.generate_variable(self.MDM.Fields[iteration_full_name], iterations=[field.Categories[iteration]])
                    
    def transform_simple_data(self, field, iterations=list()):
        var_name = self.get_variable_name(field, iterations=iterations)
        var_label = Transform.format_text(self.get_variable_label(field, iterations=iterations))

        self.varNames.append(var_name)
        self.varLabels[var_name] = var_label.encode('utf-8')
        self.varTypes[var_name] = self.get_datatype(field)
        self.measureLevels[var_name] = self.get_measure_level(field)
        
        if self.varTypes[var_name] > 0:
            self.varMissingValues[var_name] = {"values": [''] if self.varTypes[var_name] > 0 else [None]}

        if field.LevelDepth == 1:
            self.df_spss[var_name] = self.df[field.FullName]
        else:
            self.df_spss[var_name] = self.df[field.FullName.replace("..", "%s") % tuple(field.CurrentIndexPath.split(","))]
    
    def get_parent_node(self, field):
            if field.LevelDepth == 1:
                return field
            else:
                return self.get_parent_node(field.Parent)
            
    def transform_categorical_data(self, field, iterations=list()):
        var_name = field.Name if field.Properties["py_setColumnName"] is None else field.Properties["py_setColumnName"]
        var_label = Transform.format_text(self.get_variable_label(field, iterations=iterations))

        value_labels = self.get_categories_list(field, show_punching_data=field.Properties["py_showPunchingData"])
        
        categories_list = list()
        remaining_categories_list = list()
        # other_categories_list = list()

        if field.Properties["py_setCategoriesList"]:
            categories_list = field.Properties["py_setCategoriesList"].split(',')
        else:
            categories_list = [cat.Name for cat in field.Categories if not cat.IsOtherLocal]

        remaining_categories_list = [cat.Name for cat in field.Categories if cat.Name not in categories_list and not cat.IsOtherLocal]
        
        if field.Properties["py_showPunchingData"]:
            var_fullname = field.FullName if len(iterations) == 0 else field.FullName.replace("..", "%s") % tuple(field.CurrentIndexPath.split(","))

            df_updated = self.df[var_fullname].replace(to_replace="[\{\}]", value="", regex=True)

            self.df_spss = pd.concat([self.df_spss, df_updated], ignore_index=False, axis=1)
            
            attr_name = re.sub(pattern="_", repl="_C", string=re.sub(pattern=",", repl="", string=re.sub(pattern="[\{\}]",repl='',string=field.CurrentIndexPath)))
            
            for cat_name in categories_list:
                category = field.Categories[cat_name]
                
                category_name = re.sub(pattern="^_", repl="", string=category.Name)

                var_name_temp = "{}_C{}{}".format(var_name, category_name, attr_name)

                self.varNames.append(var_name_temp)
                self.varLabels[var_name_temp] = "{}_{}".format(var_label, category.Label).encode('utf-8')     
                self.varTypes[var_name_temp] = self.get_datatype(field)
                self.measureLevels[var_name_temp] = self.get_measure_level(field)
                self.valueLabels[var_name_temp] = value_labels
                
                match field.Properties["py_setVariableValues"]:
                    case "Labels":
                        self.df_spss[var_name_temp] = self.df_spss[df_updated.name].apply(lambda x: None if x is None else "Yes" if category.Name.lower() in x.split(',') else "No")
                    case _:
                        self.df_spss[var_name_temp] = self.df_spss[df_updated.name].apply(lambda x: None if x is None else 1 if category.Name.lower() in x.split(',') else 0)
            
            if len(remaining_categories_list) > 0:
                var_name_temp = "{}_C97".format(var_name)

                self.varNames.append(var_name_temp)
                self.varLabels[var_name_temp] = "{}_{}".format(var_label, category.Label).encode('utf-8')     
                self.varTypes[var_name_temp] = self.get_datatype(field)
                self.measureLevels[var_name_temp] = self.get_measure_level(field)
                self.valueLabels[var_name_temp] = value_labels

                self.df_spss = pd.concat([self.df_spss, df_updated], ignore_index=False, axis=1)
                
                match field.Properties["py_setVariableValues"]:
                    case "Names":
                        self.df_spss[var_name_temp] = self.df_spss[df_updated.name].apply(lambda x: None if x is None else 1 if any([y in remaining_categories_list for y in x.split(',')]) else 0)
                    case "Labels":
                        self.df_spss[var_name_temp] = self.df_spss[df_updated.name].apply(lambda x: None if x is None else "Yes" if any([y in remaining_categories_list for y in x.split(',')]) else "No")

                self.df_spss.drop(columns=[df_updated.name], inplace=True)

            if field.Properties["py_showHelperFields"]:
                if field.HelperFields.Count > 0:
                    df_others = pd.DataFrame()
                    df_others["Other"] = self.df[[helperfield.FullName if len(iterations) == 0 else helperfield.FullName.replace("..", "%s") % tuple(field.CurrentIndexPath.split(",")) for helperfield in field.HelperFields]].fillna('').sum(1).replace('', np.nan)
                    
                    if field.Properties["py_combibeHelperFields"]:
                        if field.LevelDepth == 1:
                            var_name_temp = "{}".format(var_name)
                        else:
                            var_name_temp = "{}{}".format(var_name, attr_name)

                        var_name_temp = "{}_C997".format(var_name_temp)              

                        self.varNames.append(var_name_temp)
                        self.varLabels[var_name_temp] = "{}_{}".format(var_label, "Other").encode('utf-8')     
                        self.varTypes[var_name_temp] = self.get_datatype(field)
                        self.measureLevels[var_name_temp] = self.get_measure_level(field)
                        self.valueLabels[var_name_temp] = value_labels
                
                        self.df_spss[var_name_temp] = df_others["Other"].apply(lambda x: 0 if pd.isna(x) else 1)
                        self.df_spss.loc[self.df_spss[df_updated.name].isnull(), var_name_temp] = None

                        if field.LevelDepth == 1:
                            var_name_temp = "{}".format(var_name)
                        else:
                            var_name_temp = "{}{}".format(var_name, attr_name)

                        var_name_temp = "{}_C997_Verbatim".format(var_name_temp)

                        self.varNames.append(var_name_temp)
                        self.varLabels[var_name_temp] = var_label.encode('utf-8')
                        self.varTypes[var_name_temp] = self.get_datatype(field.HelperFields[0], parent=field)

                        if self.varTypes[var_name_temp] == 0:
                            self.varMissingValues[var_name_temp] = {"values": [''] if self.varTypes[var_name_temp] > 0 else [None]}

                        self.measureLevels[var_name_temp] = self.get_measure_level(field.HelperFields[0])

                        self.df_spss[var_name_temp] = df_others["Other"].apply(lambda x: '' if pd.isna(x) else x)
                    else:
                        for helperfield in field.HelperFields:
                            var_name_temp = "{}_C{}".format(var_name, re.sub(pattern="^_", repl="", string=helperfield.Name))
                            self.varNames.append(var_name_temp)
                            self.varLabels[var_name_temp] = "{}_{}".format(var_label, category.Label).encode('utf-8')     
                            self.varTypes[var_name_temp] = self.get_datatype(field)
                            self.measureLevels[var_name_temp] = self.get_measure_level(field)
                            self.valueLabels[var_name_temp] = value_labels
                            
                            self.df_spss[var_name_temp] = self.df[helperfield.FullName if len(iterations) == 0 else helperfield.FullName.replace("..","%s") % tuple(field.CurrentIndexPath.split(','))].apply(lambda x: 0 if pd.isna(x) else 1)
                            self.df_spss.loc[self.df_spss[df_updated.name].isnull(), var_name_temp] = None

                            var_name_temp = "{}_C{}_Verbatim".format(var_name, re.sub(pattern="^_", repl="", string=helperfield.Name))
                            self.varNames.append(var_name_temp)
                            self.varLabels[var_name_temp] = var_label.encode('utf-8')
                            self.varTypes[var_name_temp] = self.get_datatype(helperfield, parent=field)
                            self.measureLevels[var_name_temp] = self.get_measure_level(helperfield)

                            self.df_spss[var_name_temp] = self.df[helperfield.FullName if len(iterations) == 0 else helperfield.FullName.replace("..","%s") % tuple(field.CurrentIndexPath.split(','))].apply(lambda x: '' if pd.isna(x) else x)
        
            self.df_spss.drop(columns=[df_updated.name], inplace=True)
        
        elif field.Properties["py_showVariableNames"] and field.Properties["py_showVariableLabels"]:
            replaced_categories_list = {}
            replaced_values_list = {}

            for cat in field.Categories:
                replaced_categories_list[cat.Name] = cat.Label
                replaced_values_list[cat.Name] = cat.Name if cat.Properties["value"] is None else cat.Properties["value"]

            if field.LevelDepth == 1:
                match field.Properties["py_setVariableValues"]:
                    case "Values":
                        self.df_spss[var_name] = self.df[field.FullName].apply(lambda x: np.nan if x is None else ';'.join(map(replaced_values_list.get, x[1:len(x)-1].split(','))))
                    case _:
                        self.df_spss[var_name] = self.df[field.FullName].replace(to_replace=",_", value=";", regex=True)
                        self.df_spss[var_name] = self.df_spss[var_name].replace(to_replace="[\{\}_]", value="", regex=True)

                self.df_spss[f"{var_name}_Label"] = self.df[field.FullName].apply(lambda x: np.nan if x is None else ';'.join(map(replaced_categories_list.get, x[1:len(x)-1].split(','))))
            else:
                #var_name = "{} - {}".format(var_name, field.CurrentIndexPath)
                var_fullname = field.FullName.replace("..", "%s") % tuple(field.CurrentIndexPath.split(","))
                
                match field.Properties["py_setVariableValues"]:
                    case "Values":
                        self.df_spss[var_name] = self.df[var_fullname].apply(lambda x: np.nan if x is None else ';'.join(map(replaced_values_list.get, x[1:len(x)-1].split(','))))
                    case _:
                        self.df_spss[var_name] = self.df[var_fullname].replace(to_replace=",_", value=";", regex=True)
                        self.df_spss[var_name] = self.df_spss[var_name].replace(to_replace="[\{\}_]", value="", regex=True)
                
                self.df_spss[f"{var_name}_Label"] = self.df[var_fullname].apply(lambda x: np.nan if x is None else ';'.join(map(replaced_categories_list.get, x[1:len(x)-1].split(','))))
        else:
            replaced_categories_list = self.get_replaced_categories_list(field)
            
            var_fullname = field.FullName if len(iterations) == 0 else field.FullName.replace("..", "%s") % tuple(field.CurrentIndexPath.split(","))

            attr_name = re.sub(pattern="^_", repl="", string=re.sub(pattern="[\{\},]",repl='',string=field.CurrentIndexPath)) 

            df_updated = self.df[var_fullname].replace(to_replace="[\{\}]", value="", regex=True)
            df_updated = df_updated.str.split(',', expand=True)
            # df_updated = df_updated[list(df_updated.columns)].replace(to_replace="^_", value="", regex=True)

            column_renamed = dict()

            for i in list(df_updated.columns):
                if field.LevelDepth == 1:
                    if field.MinValue == 1 and field.MaxValue == 1:
                        var_name_temp = "{}".format(var_name)
                    else: 
                        var_name_temp = "{}_{}".format(var_name, i + 1)
                else:
                    if field.MinValue == 1 and field.MaxValue == 1:
                        var_name_temp = "{}C{}".format(var_name, attr_name)
                    else: 
                        var_name_temp = "{}_{}_C{}".format(var_name, i + 1, attr_name)

                self.varNames.append(var_name_temp)
                self.varLabels[var_name_temp] = var_label.encode('utf-8')
                self.varTypes[var_name_temp] = self.get_datatype(field)
                self.measureLevels[var_name_temp] = self.get_measure_level(field)
                self.valueLabels[var_name_temp] = value_labels

                column_renamed[i] = var_name_temp
            
            df_updated.rename(columns=column_renamed, inplace=True)
            df_updated.replace(replaced_categories_list, inplace=True)

            self.df_spss = pd.concat([self.df_spss, df_updated], ignore_index=False, axis=1)

            if field.Properties["py_showHelperFields"]:
                if field.HelperFields.Count > 0:
                    df_others = pd.DataFrame()
                    df_others["Other"] = self.df[[helperfield.FullName for helperfield in field.HelperFields]].fillna('').sum(1).replace('', np.nan)

                    if field.Properties["py_combibeHelperFields"]:
                        var_name_temp = "{}_C{}_Verbatim".format(var_name, re.sub(pattern="^_", repl="", string=helperfield.Name))
                        self.varNames.append(var_name_temp)
                        self.varLabels[var_name_temp] = var_label.encode('utf-8')
                        self.varTypes[var_name_temp] = self.get_datatype(helperfield)
                        self.measureLevels[var_name_temp] = self.get_measure_level(helperfield)

                        self.df_spss[var_name_temp] = self.df[helperfield.FullName].apply(lambda x: '' if pd.isna(x) else x)
                    else:
                        for helperfield in field.HelperFields:
                            var_name_temp = "{}_C{}".format(var_name, re.sub(pattern="^_", repl="", string=helperfield.Name))
                            self.varNames.append(var_name_temp)
                            self.varLabels[var_name_temp] = var_label.encode('utf-8')
                            self.varTypes[var_name_temp] = self.get_datatype(helperfield)
                            self.measureLevels[var_name_temp] = self.get_measure_level(helperfield)

                            self.df_spss[var_name_temp] = self.df[helperfield.FullName]

    def get_replaced_categories_list(self, field):
        replaced_categories_list = dict()

        index = 1

        for cat in field.Categories:
            cat_value = str(field.Categories[cat.Name].Properties["value"])

            if cat_value.isnumeric():
                cat_value = int(cat_value)
            else:
                if re.match(pattern='^\D\d+', string=cat_value):
                    cat_value = int(cat_value[1:len(cat_value)])
                else:
                    cat_value = index
                    
            replaced_categories_list[cat.Name.lower()] = cat_value
            
            index = index + 1
        
        return replaced_categories_list
    
    def get_categories_list(self, field, show_punching_data=False):
        categories_list = dict()

        if show_punching_data:
            categories_list[0] = "No".encode('utf-8')
            categories_list[1] = "Yes".encode('utf-8')            
        else: 
            index = 1

            for cat in field.Categories:
                cat_value = str(field.Categories[cat.Name].Properties["value"])

                if cat_value.isnumeric():
                    cat_value = int(cat_value)
                else:
                    if re.match(pattern='^\D\d+', string=cat_value):
                        cat_value = int(cat_value[1:len(cat_value)])
                    else:
                        cat_value = index
                        
                categories_list[cat_value] = Transform.format_text(cat.Label).encode('utf-8')
                
                index = index + 1
        
        return categories_list

    def get_measure_level(self, field):
        match field.DataType:
            case dataTypeConstants.mtLong.value | dataTypeConstants.mtDouble.value:
                return "scale"
            case dataTypeConstants.mtText.value:
                return "nominal"
            case _:
                return "nominal"
            
    def get_datatype(self, field, parent = None):
        match field.DataType:
            case dataTypeConstants.mtLong.value | dataTypeConstants.mtDouble.value:
                return 0
            case dataTypeConstants.mtText.value:
                if field.LevelDepth == 1:
                    max_len = self.df[field.FullName].str.encode('utf-8').replace(r'\xcd',r'\xcc\xa6').str.decode('utf-8').str.len().max()
                else:
                    if field.UsageTypeName == 'OtherSpecify':
                        max_len = self.df[field.FullName.replace("..", "%s") % tuple(parent.CurrentIndexPath.split(","))].fillna("").str.len().max()
                    else:
                        max_len = self.df[field.FullName.replace("..", "%s") % tuple(field.CurrentIndexPath.split(","))].fillna("").str.len().max()
                
                return 1024 if pd.isnull(max_len) else int(max_len)
            case dataTypeConstants.mtDate.value:
                return 0
            case _:
                return 0

    def get_iteration_name1(self, iterations=list()):
        labels = list()

        def get_label(index):
            if index < 0:
                return

            labels.append(iterations[index].Name)
            get_label(index - 1) 
        
        get_label(len(iterations) - 1)

        ls = labels[1:len(labels)]
        ls.append(labels[0])
        return "_".join([l if l[0:1] not in ["_"] else l[1:len(l)] for l in ls])
    
    def get_iteration_name(self, iterations=None):
        if iterations is None:
            iterations = []
        
        labels = []

        if len(iterations) == 1:
            labels.append(iterations[0].Name)
        elif len(iterations) > 1:
            labels.extend(self.get_iteration_name1(iterations=iterations))  # Ensure this returns a list

        return labels
    
    def get_variable_name(self, field, iterations=list()):
        if len(iterations) == 0:
            var_name = field.FullName if field.Properties["py_setColumnName"] is None else field.Properties["py_setColumnName"]
        else:
            if field.Properties["py_setColumnName"] is None:
                var_name = field.FullName.replace("..","%s") % tuple(field.CurrentIndexPath.split(','))
            else:
                var_name = "%s%s" % (field.Properties["py_setColumnName"], "".join(self.get_iteration_name(iterations=iterations)))
                
        return var_name

    def get_iteration_label(self, iterations=list()):
        labels = list()

        def get_label(index):
            if index < 0:
                return

            labels.append(iterations[index].Label)
            get_label(index - 1) 
        
        get_label(len(iterations) - 1)
        return "_".join(labels)

    def get_variable_label(self, field, iterations=list()):
        m = re.match(pattern="^(.*)[\.](.*)\?", string= field.Label)
        s = field.Label if m is None else field.Label[m.regs[0][0]:m.regs[0][1]]
        
        if len(iterations) > 0:
            s = "{} - {}".format(s, self.get_iteration_label(iterations=iterations))
        return s

    def to_excel_wide_to_long(self):
        df = pd.DataFrame(data=self.df_spss, columns=self.varNames)
        attributes = self.get_categories_list(self.MDM.Fields[self.group_name])



        #Columns to use as id variable
        self.id_vars = list()
        self.value_groupnames = list()
        self.groupname_labels = list()
        
        if self.group_name is not None:
            self.value_groupnames.extend(self.get_categories_list(self.MDM.Fields[self.group_name]).keys())

        


        df_unpivot = pd.wide_to_long(df, stubnames=self.groupname_labels, i=self.id_vars, j='Rotation', sep="#", suffix="(({}))$".format("|".join([str(c) for c in self.value_groupnames])))

        df_unpivot.reset_index(inplace=True)

        writer = pd.ExcelWriter("output.xlsx", engine="xlsxwriter")

        df_unpivot.to_excel(writer, sheet_name="Data 1")

        writer.close()

    def to_spss(self):
        
        with savReaderWriter.SavWriter(self.mdd_file.replace(".mdd", "_SPSS.sav"), varNames=self.varNames, varTypes=self.varTypes, formats=self.var_date_formats, varLabels=self.varLabels, measureLevels=self.measureLevels, valueLabels=self.valueLabels, ioUtf8=True) as writer:
            for i, row in tqdm(self.df_spss.iterrows(), desc="Insert data...") :
                clean_row = []

                for var in self.varNames:
                    value = row.get(var)

                    # Nếu là ngày thì xử lý như trước
                    if var in self.var_dates and not pd.isnull(value):
                        # Xử lý định dạng ngày
                        if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', str(value)):
                            fmt = '%m/%d/%Y'
                        elif re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', str(value)):
                            fmt = '%Y/%m/%d'
                        elif re.match(r'^\d{1,2}:\d{1,2}:\d{1,2}$', str(value)):
                            fmt = '%H:%M:%S'
                        elif re.match(r'^\d{1,2}:\d{1,2}$', str(value)):
                            fmt = '%H:%M'
                        else:
                            fmt = None

                        if fmt:
                            try:
                                d = datetime.strptime(str(value), fmt)
                                value = writer.spssDateTime(d.strftime(fmt).encode('utf-8'), fmt)
                            except:
                                value = None

                    # Chuẩn hóa giá trị:
                    if pd.isnull(value):
                        if self.varTypes[var] > 0:  # String
                            value = ''
                        else:  # Numeric
                            value = None
                    elif self.varTypes[var] > 0 and str(value).strip() == '':
                        value = ''

                    clean_row.append(value)

                writer.writerow(clean_row)
    
    def to_spss_wide_to_long(self):
        df = pd.DataFrame(data=self.records, columns=self.varNames)

        df_unpivot = pd.wide_to_long(df, stubnames=self.groupname_labels, i=self.id_vars, j='Rotation', sep="#", suffix="(({}))$".format("|".join([str(c) for c in self.value_groupnames])))
        df_unpivot.reset_index(inplace=True)
        
        var_names_unpivot = list()
        var_types_unpivot = dict()
        formats_unpivot = dict()
        var_labels_unpivot = dict()
        measure_levels_unpivot = dict()
        value_labels_unpivot = dict()
        var_dates_unpivot = list()

        for c in list(df_unpivot.columns):
            if c == "Rotation":
                var_names_unpivot.append(c)
                var_types_unpivot[c] = 10
            else:
                for v in self.varNames:
                    variable = re.sub(pattern="(#({}))$".format("|".join([str(i) for i in self.value_groupnames])), repl="", string=v)
                    
                    if c == variable and variable not in var_names_unpivot:
                        var_names_unpivot.append(variable)
                        
                        var_type_value = self.varTypes[v]

                        if isinstance(var_type_value, int):  # Ensure string width is correct
                            var_types_unpivot[variable] = max(var_type_value, 0)  # Ensure no negative values
                        else:
                            var_types_unpivot[variable] = 0  # Default to numeric type if unexpected type
                            
                        if v in self.var_date_formats.keys():
                            formats_unpivot[variable] = self.var_date_formats[v]
                        if v in self.varLabels.keys():
                            var_labels_unpivot[variable] = self.varLabels[v]
                        if v in self.measureLevels.keys():
                            measure_levels_unpivot[variable] = self.measureLevels[v]
                        if v in self.valueLabels.keys():
                            value_labels_unpivot[variable] = self.valueLabels[v]
                        if v in self.var_dates:
                            var_dates_unpivot.append(c)
                        break
        
        with savReaderWriter.SavWriter(self.mdd_file.replace(".mdd", "unpivot.sav"), varNames=var_names_unpivot, varTypes=var_types_unpivot, formats=formats_unpivot, varLabels=var_labels_unpivot, measureLevels=measure_levels_unpivot, valueLabels=value_labels_unpivot, ioUtf8=True) as writer:
            for i, row in df_unpivot.iterrows():
                for v in var_dates_unpivot:
                    if re.match(pattern="(.*)DATE(.*)", string=v):
                        try:
                            d = datetime.strptime(row[v], "%m/%d/%Y")
                            row[v] = writer.spssDateTime(datetime.strftime(d, "%m/%d/%Y").encode('utf-8'), "%m/%d/%Y")
                        except:
                            row[v] = np.nan
                        
                    if re.match(pattern="(.*)TIME(.*)", string=v):
                        try:
                            d = datetime.strptime(row[v], "%H:%M:%S")
                            row[v] = writer.convertTime(0, d.hour, d.minute, d.second)
                        except:
                            row[v] = np.nan

                writer.writerow([None if pd.isnull(d) else str(d) if not str(d).isnumeric() else str(float(d)) for d in row])