import snowflake.connector
import xml.etree.ElementTree as ET
import pandas as pd
import requests
import json



#------------------------------------------------------------------
#function returns a cursor object that allows you to make snowsql queries
def authenticate_snowflake(snow_u,snow_p,account_name,database_name):
    ctx = snowflake.connector.connect(
        user=snow_u,
        password=snow_p,
        account=account_name,
        database=database_name
        )
    cs = ctx.cursor()
    return(cs)
#---------------------------------------------------------------------
#function returns a temp token different than your PAT
#that you must use in every REST API call. This expires after some time.
#It will be important to run this each session.
def authenticate_tableau(url_name,PAT,site_name, token_name):
    url = "https://" + url_name + "/api/3.16/auth/signin"

    payload = json.dumps({
      "credentials": {
        "personalAccessTokenName": token_name,
        "personalAccessTokenSecret": PAT,
        "site": {
          "contentUrl": site_name
        }
      }
    })
    headers = {
      'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    
    #parsing site id and token with xml parser.
    parse = ET.fromstring(response.text)
    site_id = parse.find('.//{http://tableau.com/api}site').attrib['id']
    token = parse.find('.//{http://tableau.com/api}credentials').attrib['token']

    req_strings=[token,site_id]
    return(req_strings)
#---------------------------------------------------------------------
#use the Metadata API (different from REST API) to get a list of snowflake tables
def get_table_luids(url_name, database_name, token):
    mdapi_query = '''
    query get_databases {
    databases (filter: {connectionType: "snowflake", name:"''' + database_name + '''"}){
    name
    id
    tables{
        name
        id
        luid
    
    }

    
    }
    }
    '''
    auth_headers = auth_headers = {'accept': 'application/json','content-type': 'application/json','x-tableau-auth': token}
    metadata_query = requests.post('https://'+url_name+ '/api/metadata/graphql', headers = auth_headers, verify=True, json = {"query": mdapi_query})
    mdapi_result = json.loads(metadata_query.text)

    #while loop to parse through the json and get a dictionary {table name:LUID}
    k=0
    table_luid_list = []
    table_name_list = []
    table_id_list = []
    while k < len(mdapi_result['data']['databases'][0]['tables']):
        print(mdapi_result['data']['databases'][0]['tables'][k]['luid'])
        table_luid_list.append(mdapi_result['data']['databases'][0]['tables'][k]['luid'])
        table_name_list.append(mdapi_result['data']['databases'][0]['tables'][k]['name'])
        table_id_list.append(mdapi_result['data']['databases'][0]['tables'][k]['id'])

        k = k+1
        
    table_dictionary = {"table_name":table_name_list, "table_luid":table_luid_list, "table_id":table_id_list}
    tableau_tables_info = pd.DataFrame(table_dictionary, columns=['table_name','table_luid', 'table_id'])
    #return dictionary
    return(tableau_tables_info)
#---------------------------------------------------------------------
#use this if you know the table name is unique, and if you can't get LUID from metadata API
def get_table_id(tab_url, table_name, site_id, token):
    get_tables_url = "https://"+tab_url+"/api/3.13/sites/"+site_id+"/tables"

    payload = ""
    headers = {
      'X-Tableau-Auth': token
    }

    table_response = requests.request("GET", get_tables_url, headers=headers, data=payload)
    #parse through response text to get table luid
    table_id_string = table_response.text.split('name="'+table_name+'"',1)
    table_id_string_split1 = table_id_string[0].split('<table id="')
    table_id_string_split2 = table_id_string_split1[-1]
    table_id_string_split3 = table_id_string_split2[0:-1]
    table_id_string_split4 = table_id_string_split2[0:-2]
    return(table_id_string_split4)
#---------------------------------------------------------------------
#function to return list of columns and column ids
#need both of these arguments to add a description in catalog
def get_list_of_columns(url_name,table_id,site_id,token):
    get_columns_url = "https://"+url_name+"/api/3.16/sites/"+site_id+"/tables/"+table_id+'/columns'

    payload = ""
    headers = {
      'X-Tableau-Auth': token
    }

    columns_response = requests.request("GET", get_columns_url, headers=headers, data=payload)
    parse = ET.fromstring(columns_response.content)

    column_names_list = []
    column_ids_list = []
    for column in parse.iter('{http://tableau.com/api}column'):
        column_ids_list.append(column.attrib['id'])
        column_names_list.append(column.attrib['name'])

    column_dictionary = {"column_name":column_names_list, "column_id":column_ids_list}
    tableau_column_info = pd.DataFrame(column_dictionary, columns=['column_name','column_id'])
    return(tableau_column_info)
#---------------------------------------------------------------------
#function to get all column names and comments from a table
def get_snow_descriptions(cursor_object, table_name):
    desc_table_pandas = cursor_object.execute("select column_name, comment from information_schema.columns where table_name = '"+table_name+"';").fetch_pandas_all()
    return(desc_table_pandas)
#---------------------------------------------------------------------
#join descriptions and column ids on column names
def add_comments_to_tab_table(tableau_columns, snow_columns):
    join_result = tableau_columns.merge(snow_columns, how='inner',left_on="column_name",right_on='COLUMN_NAME')
    
    return(join_result)
#---------------------------------------------------------------------
#function to publish 1 specific comment to a column in tableau
def publish_description_to_column(tab_url, site_id, table_id,column_id, description_text,token):
    #post description to tableau catalog
    column_description_url = "https://"+tab_url+"/api/3.16/sites/"+site_id+"/tables/" + table_id + "/columns/" + column_id

    payload = "<tsRequest>\n  <column description=\"" + description_text +" \">\n  </column>\n</tsRequest>"
    headers = {
        'X-Tableau-Auth': token,
      'Content-Type': 'text/plain'
    }

    column_description_response = requests.request("PUT", column_description_url, headers=headers, data=payload)

    column_description_response_code = column_description_response.text
    return

#---------------------------------------------------------------------
#function to publish all column comments to the right tables descriptions in tableau
def update_table_descriptions(tab_url, site_id, tab_data_frame, table_id, token):
    for index, rows in tab_data_frame.iterrows():
        if rows['COMMENT'] != None:
            publish_description_to_column(tab_url, site_id, table_id,rows['column_id'], rows['COMMENT'],token)
    return
#--------------------------------------------------------------------