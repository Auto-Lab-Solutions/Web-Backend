"""
Analytics Manager for Business Intelligence Operations

This module provides comprehensive analytics functionality for Auto Lab Solutions system,
analyzing transaction data from the Invoices table's analyticsData field and other sources.
All date/time operations use Australia/Perth timezone.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict, Counter
from decimal import Decimal

import db_utils as db
from data_access_utils import DataAccessManager
from exceptions import BusinessLogicError


class AnalyticsManager(DataAccessManager):
    """Manager for analytics and business intelligence operations"""
    
    def __init__(self):
        super().__init__()
    
    def get_comprehensive_analytics(self, start_date_str, end_date_str, analytics_type=None):
        """
        Get comprehensive analytics data for dashboard visualization
        
        NOTE: All date-related operations (filtering, sorting, grouping) use 'effectiveDate' 
        from operation_data instead of createdAt or payment date fields.
        
        Args:
            start_date_str: Start date in YYYY-MM-DD format
            end_date_str: End date in YYYY-MM-DD format
            analytics_type: Optional filter for specific analytics type
            
        Returns:
            dict: Comprehensive analytics data including revenue, transactions, trends, etc.
        """
        # Validate date range (max 365 days for comprehensive analytics)
        start_timestamp, end_timestamp = self.validate_date_range(
            start_date_str, end_date_str, max_days=365
        )
        
        # Get all invoices with analytics data in the date range
        invoices = db.get_invoices_by_date_range(start_timestamp, end_timestamp, limit=5000)
        
        # Filter invoices with valid analytics data
        valid_invoices = [
            invoice for invoice in invoices 
            if invoice.get('analyticsData') and 
               invoice.get('analyticsData', {}).get('operation_data')
        ]
        
        analytics_result = {
            'period': {
                'start_date': start_date_str,
                'end_date': end_date_str,
                'total_days': (datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=ZoneInfo('Australia/Perth')) - 
                              datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=ZoneInfo('Australia/Perth'))).days + 1
            },
            'summary': self._calculate_summary_metrics(valid_invoices),
            'revenue_analytics': self._calculate_revenue_analytics(valid_invoices, start_date_str, end_date_str),
            'service_analytics': self._calculate_service_analytics(valid_invoices),
            'product_analytics': self._calculate_product_analytics(valid_invoices),
            'customer_analytics': self._calculate_customer_analytics(valid_invoices),
            'vehicle_analytics': self._calculate_vehicle_analytics(valid_invoices),
            'payment_analytics': self._calculate_payment_analytics(valid_invoices),
            'booking_analytics': self._calculate_booking_analytics(valid_invoices),
            'trend_analytics': self._calculate_trend_analytics(valid_invoices, start_date_str, end_date_str),
            'operational_metrics': self._calculate_operational_metrics(valid_invoices),
            'metadata': {
                'total_invoices_analyzed': len(valid_invoices),
                'total_invoices_in_period': len(invoices),
                'analysis_timestamp': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
                'currency': 'AUD'  # Assuming Australian Dollar based on system context
            }
        }
        
        # Apply analytics type filter if specified
        if analytics_type:
            filtered_result = self._filter_analytics_by_type(analytics_result, analytics_type)
            return filtered_result
        
        return analytics_result
    
    def _calculate_summary_metrics(self, invoices):
        """Calculate high-level summary metrics"""
        total_revenue = 0
        total_transactions = len(invoices)
        service_revenue = 0
        product_revenue = 0
        pre_booked_count = 0
        non_booked_count = 0
        
        for invoice in invoices:
            operation_data = invoice.get('analyticsData', {}).get('operation_data', {})
            
            # Calculate revenue from payment details
            payment_amount = float(operation_data.get('paymentDetails', {}).get('amount', '0'))
            total_revenue += payment_amount
            
            # Separate service and product revenue
            services = operation_data.get('services', [])
            orders = operation_data.get('orders', [])
            
            for service in services:
                service_revenue += float(service.get('price', '0'))
            
            for order in orders:
                product_revenue += float(order.get('total_price', '0'))
            
            # Count booking types
            booked_by = operation_data.get('bookingDetails', {}).get('bookedBy', 'NONE')
            if booked_by == 'NONE':
                non_booked_count += 1
            else:
                pre_booked_count += 1
        
        avg_transaction_value = total_revenue / total_transactions if total_transactions > 0 else 0
        
        return {
            'total_revenue': round(total_revenue, 2),
            'total_transactions': total_transactions,
            'average_transaction_value': round(avg_transaction_value, 2),
            'service_revenue': round(service_revenue, 2),
            'product_revenue': round(product_revenue, 2),
            'pre_booked_transactions': pre_booked_count,
            'non_booked_transactions': non_booked_count,
            'service_vs_product_ratio': {
                'service_percentage': round((service_revenue / total_revenue * 100), 2) if total_revenue > 0 else 0,
                'product_percentage': round((product_revenue / total_revenue * 100), 2) if total_revenue > 0 else 0
            }
        }
    
    def _calculate_revenue_analytics(self, invoices, start_date_str, end_date_str):
        """Calculate detailed revenue analytics with time-based trends using effectiveDate"""
        daily_revenue = defaultdict(float)
        monthly_revenue = defaultdict(float)
        payment_method_revenue = defaultdict(float)
        
        for invoice in invoices:
            operation_data = invoice.get('analyticsData', {}).get('operation_data', {})
            payment_details = operation_data.get('paymentDetails', {})
            
            amount = float(payment_details.get('amount', '0'))
            payment_method = payment_details.get('payment_method', 'unknown')
            
            # Use effectiveDate instead of payment date for all revenue analytics
            effective_date = operation_data.get('effectiveDate', '')
            
            if effective_date:
                try:
                    # Convert from DD/MM/YYYY to YYYY-MM-DD for consistency
                    day, month, year = effective_date.split('/')
                    normalized_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    month_key = f"{year}-{month.zfill(2)}"
                    
                    daily_revenue[normalized_date] += amount
                    monthly_revenue[month_key] += amount
                except ValueError:
                    # If effectiveDate format is invalid, use fallback
                    creation_timestamp = invoice.get('createdAt', 0)
                    if creation_timestamp:
                        fallback_date = datetime.fromtimestamp(creation_timestamp, ZoneInfo('Australia/Perth')).strftime('%Y-%m-%d')
                        daily_revenue[fallback_date] += amount
                        monthly_revenue[fallback_date[:7]] += amount
            else:
                # Use invoice creation date as fallback if no effectiveDate
                creation_timestamp = invoice.get('createdAt', 0)
                if creation_timestamp:
                    fallback_date = datetime.fromtimestamp(creation_timestamp, ZoneInfo('Australia/Perth')).strftime('%Y-%m-%d')
                    daily_revenue[fallback_date] += amount
                    monthly_revenue[fallback_date[:7]] += amount
            
            payment_method_revenue[payment_method] += amount
        
        # Calculate growth metrics
        revenue_trend = self._calculate_revenue_growth(daily_revenue, start_date_str, end_date_str)
        
        return {
            'daily_breakdown': dict(daily_revenue),
            'monthly_breakdown': dict(monthly_revenue),
            'payment_method_breakdown': dict(payment_method_revenue),
            'trend_analysis': revenue_trend,
            'peak_day': max(daily_revenue.items(), key=lambda x: x[1]) if daily_revenue else ('N/A', 0),
            'peak_month': max(monthly_revenue.items(), key=lambda x: x[1]) if monthly_revenue else ('N/A', 0)
        }
    
    def _calculate_service_analytics(self, invoices):
        """Calculate detailed service analytics with pre-booked/walk-in breakdown for frontend table"""
        # Structure: {service_name: {preBookedCount, preBookedRevenue, walkInCount, walkInRevenue}}
        service_stats = {}
        for invoice in invoices:
            operation_data = invoice.get('analyticsData', {}).get('operation_data', {})
            services = operation_data.get('services', [])
            booked_by = operation_data.get('bookingDetails', {}).get('bookedBy', 'NONE')
            is_prebooked = booked_by != 'NONE'
            for service in services:
                service_name = service.get('service_name', 'Unknown Service')
                price = float(service.get('price', '0'))
                if service_name not in service_stats:
                    service_stats[service_name] = {
                        'service': service_name,
                        'preBookedCount': 0,
                        'preBookedRevenue': 0.0,
                        'walkInCount': 0,
                        'walkInRevenue': 0.0
                    }
                if is_prebooked:
                    service_stats[service_name]['preBookedCount'] += 1
                    service_stats[service_name]['preBookedRevenue'] += price
                else:
                    service_stats[service_name]['walkInCount'] += 1
                    service_stats[service_name]['walkInRevenue'] += price
        # Calculate preBookedRate for each service
        for stats in service_stats.values():
            total_count = stats['preBookedCount'] + stats['walkInCount']
            stats['preBookedRate'] = round(
                (stats['preBookedCount'] / total_count * 100) if total_count > 0 else 0, 2
            )
            stats['preBookedRevenue'] = round(stats['preBookedRevenue'], 2)
            stats['walkInRevenue'] = round(stats['walkInRevenue'], 2)
        # Return as a list sorted by total revenue (preBooked + walkIn)
        service_table = sorted(
            service_stats.values(),
            key=lambda x: x['preBookedRevenue'] + x['walkInRevenue'],
            reverse=True
        )
        return {
            'service_table': service_table,
            'total_unique_services': len(service_stats)
        }
    
    def _calculate_product_analytics(self, invoices):
        """Calculate detailed product/item analytics"""
        product_popularity = Counter()
        product_revenue = defaultdict(float)
        product_quantities = defaultdict(int)
        category_analysis = defaultdict(lambda: {'count': 0, 'revenue': 0, 'quantity': 0})
        
        for invoice in invoices:
            operation_data = invoice.get('analyticsData', {}).get('operation_data', {})
            orders = operation_data.get('orders', [])
            
            for order in orders:
                item_name = order.get('item_name', 'Unknown Item')
                total_price = float(order.get('total_price', '0'))
                quantity = int(order.get('quantity', '1'))
                unit_price = float(order.get('unit_price', '0'))
                
                product_popularity[item_name] += quantity
                product_revenue[item_name] += total_price
                product_quantities[item_name] += quantity
                
                # Extract category from item name (first word typically)
                category = item_name.split(' ')[0] if item_name else 'Unknown'
                category_analysis[category]['count'] += 1
                category_analysis[category]['revenue'] += total_price
                category_analysis[category]['quantity'] += quantity
        
        # Calculate average unit prices
        avg_unit_prices = {}
        for item_name, total_revenue in product_revenue.items():
            total_qty = product_quantities[item_name]
            avg_unit_prices[item_name] = round(total_revenue / total_qty, 2) if total_qty > 0 else 0
        
        return {
            'most_popular_products': dict(product_popularity.most_common(10)),
            'product_revenue_breakdown': dict(product_revenue),
            'total_quantities_sold': dict(product_quantities),
            'average_unit_prices': avg_unit_prices,
            'category_analysis': dict(category_analysis),
            'top_revenue_products': sorted(
                product_revenue.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10],
            'total_unique_products': len(product_popularity)
        }
    
    def _calculate_customer_analytics(self, invoices):
        """Calculate customer behavior analytics"""
        customer_transactions = defaultdict(int)
        customer_revenue = defaultdict(float)
        customer_domains = Counter()
        
        for invoice in invoices:
            operation_data = invoice.get('analyticsData', {}).get('operation_data', {})
            customer_id = operation_data.get('customerId', '')
            amount = float(operation_data.get('paymentDetails', {}).get('amount', '0'))
            # Only count as unique customer if customer_id is a non-empty, valid email
            if customer_id and isinstance(customer_id, str) and '@' in customer_id and '.' in customer_id.split('@')[-1]:
                customer_transactions[customer_id] += 1
                customer_revenue[customer_id] += amount
                # Extract domain for business vs personal analysis
                domain = customer_id.split('@')[1].lower()
                customer_domains[domain] += 1
        
        # Calculate customer value segments
        customer_lifetime_values = dict(customer_revenue)
        avg_customer_value = sum(customer_revenue.values()) / len(customer_revenue) if customer_revenue else 0
        
        # Segment customers
        high_value_customers = {k: v for k, v in customer_revenue.items() if v > avg_customer_value * 2}
        repeat_customers = {k: v for k, v in customer_transactions.items() if v > 1}
        
        return {
            'total_unique_customers': len(customer_transactions),
            'average_customer_value': round(avg_customer_value, 2),
            'customer_transaction_counts': dict(customer_transactions),
            'customer_lifetime_values': customer_lifetime_values,
            'repeat_customers': dict(repeat_customers),
            'top_customers_by_revenue': sorted(
                customer_revenue.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10],
            'customer_retention_rate': round(
                (len(repeat_customers) / len(customer_transactions) * 100), 2
            ) if customer_transactions else 0,
            'domain_analysis': dict(customer_domains.most_common(10))
        }
    
    def _calculate_vehicle_analytics(self, invoices):
        """Calculate vehicle-related analytics"""
        vehicle_makes = Counter()
        vehicle_models = Counter()
        vehicle_years = Counter()
        make_model_combinations = Counter()
        
        for invoice in invoices:
            operation_data = invoice.get('analyticsData', {}).get('operation_data', {})
            vehicle_details = operation_data.get('vehicleDetails', {})

            make = vehicle_details.get('make', '')
            model = vehicle_details.get('model', '')
            year = vehicle_details.get('year', '')

            # Handle make field - ensure it's a string and strip whitespace
            if isinstance(make, str):
                make = make.strip()
            elif make:
                make = str(make).strip()

            # Handle model field - ensure it's a string and strip whitespace
            if isinstance(model, str):
                model = model.strip()
            elif model:
                model = str(model).strip()

            # Handle year field - can be string or integer
            if isinstance(year, str):
                year = year.strip()
            elif isinstance(year, (int, float)):
                year = str(int(year))
            else:
                year = ''

            # Only count valid years (4 digits, not '0', not empty, not in the future)
            valid_year = False
            if year and year.isdigit() and len(year) == 4 and year != '0':
                year_int = int(year)
                current_year = datetime.now(ZoneInfo('Australia/Perth')).year
                if 1900 <= year_int <= current_year:
                    valid_year = True

            if make:
                vehicle_makes[make] += 1
            if model:
                vehicle_models[model] += 1
            if valid_year:
                vehicle_years[year] += 1
            if make and model:
                make_model_combinations[f"{make} {model}"] += 1

        # Calculate average vehicle age
        vehicle_ages = []
        current_year = datetime.now(ZoneInfo('Australia/Perth')).year
        for year_str, count in vehicle_years.items():
            try:
                year_int = int(year_str)
                age = current_year - year_int
                if 0 <= age < 100:  # Only count reasonable ages
                    vehicle_ages.extend([age] * count)
            except ValueError:
                continue

        avg_vehicle_age = sum(vehicle_ages) / len(vehicle_ages) if vehicle_ages else 0
        
        return {
            'popular_makes': dict(vehicle_makes.most_common(10)),
            'popular_models': dict(vehicle_models.most_common(10)),
            'popular_years': dict(vehicle_years.most_common(10)),
            'popular_make_model_combinations': dict(make_model_combinations.most_common(10)),
            'average_vehicle_age': round(avg_vehicle_age, 1),
            'total_unique_makes': len(vehicle_makes),
            'total_unique_models': len(vehicle_models),
            'vehicle_age_distribution': self._calculate_age_distribution(vehicle_ages)
        }
    
    def _calculate_payment_analytics(self, invoices):
        """Calculate payment method and timing analytics"""
        payment_methods = Counter()
        payment_timing = {'before_operation': 0, 'after_operation': 0}
        payment_amounts_by_method = defaultdict(list)
        
        for invoice in invoices:
            operation_data = invoice.get('analyticsData', {}).get('operation_data', {})
            payment_details = operation_data.get('paymentDetails', {})
            
            method = payment_details.get('payment_method', 'unknown')
            amount = float(payment_details.get('amount', '0'))
            paid_before = payment_details.get('paid_before_operation', 0)
            
            payment_methods[method] += 1
            payment_amounts_by_method[method].append(amount)
            
            if paid_before:
                payment_timing['before_operation'] += 1
            else:
                payment_timing['after_operation'] += 1
        
        # Calculate average amounts by payment method
        avg_amounts_by_method = {}
        for method, amounts in payment_amounts_by_method.items():
            avg_amounts_by_method[method] = round(sum(amounts) / len(amounts), 2) if amounts else 0
        
        return {
            'payment_method_distribution': dict(payment_methods),
            'payment_timing_analysis': payment_timing,
            'average_amounts_by_method': avg_amounts_by_method,
            'payment_timing_percentage': {
                'before_operation_percentage': round(
                    (payment_timing['before_operation'] / len(invoices) * 100), 2
                ) if invoices else 0,
                'after_operation_percentage': round(
                    (payment_timing['after_operation'] / len(invoices) * 100), 2
                ) if invoices else 0
            },
            'preferred_payment_method': payment_methods.most_common(1)[0] if payment_methods else ('N/A', 0)
        }
    
    def _calculate_booking_analytics(self, invoices):
        """Calculate booking behavior analytics"""
        booking_types = Counter()
        staff_bookings = 0
        user_bookings = 0
        no_booking = 0
        
        booking_timing_analysis = defaultdict(int)
        
        for invoice in invoices:
            operation_data = invoice.get('analyticsData', {}).get('operation_data', {})
            booking_details = operation_data.get('bookingDetails', {})
            
            booked_by = booking_details.get('bookedBy', 'NONE')
            booking_types[booked_by] += 1
            
            if booked_by == 'STAFF':
                staff_bookings += 1
            elif booked_by == 'NONE':
                no_booking += 1
            else:
                user_bookings += 1
            
            # Analyze booking timing patterns
            booked_date = booking_details.get('bookedDate', '')
            if booked_date:
                try:
                    booking_date = datetime.strptime(booked_date, '%Y-%m-%d').replace(tzinfo=ZoneInfo('Australia/Perth'))
                    day_of_week = booking_date.strftime('%A')
                    booking_timing_analysis[day_of_week] += 1
                except ValueError:
                    pass
        
        total_transactions = len(invoices)
        
        return {
            'booking_type_distribution': dict(booking_types),
            'booking_statistics': {
                'staff_initiated': staff_bookings,
                'user_initiated': user_bookings,
                'walk_in_non_booked': no_booking,
                'pre_booking_rate': round(
                    ((staff_bookings + user_bookings) / total_transactions * 100), 2
                ) if total_transactions > 0 else 0
            },
            'booking_day_patterns': dict(booking_timing_analysis),
            'popular_booking_day': max(booking_timing_analysis.items(), key=lambda x: x[1])[0] if booking_timing_analysis else 'N/A'
        }
    
    def _calculate_trend_analytics(self, invoices, start_date_str, end_date_str):
        """Calculate trend analytics over time using effectiveDate"""
        # Group transactions by date for trend analysis using effectiveDate
        daily_data = defaultdict(lambda: {
            'transaction_count': 0, 
            'revenue': 0, 
            'service_count': 0, 
            'product_count': 0
        })
        
        weekly_data = defaultdict(lambda: {
            'transaction_count': 0, 
            'revenue': 0, 
            'service_count': 0, 
            'product_count': 0
        })
        
        for invoice in invoices:
            operation_data = invoice.get('analyticsData', {}).get('operation_data', {})
            amount = float(operation_data.get('paymentDetails', {}).get('amount', '0'))
            
            # Use effectiveDate for trend analysis
            effective_date = operation_data.get('effectiveDate', '')
            date_obj = None
            
            if effective_date:
                try:
                    # Convert from DD/MM/YYYY to date object
                    day, month, year = effective_date.split('/')
                    date_obj = datetime(int(year), int(month), int(day))
                except ValueError:
                    # Fall back to createdAt if effectiveDate is invalid
                    creation_timestamp = invoice.get('createdAt', 0)
                    if creation_timestamp:
                        date_obj = datetime.fromtimestamp(creation_timestamp, ZoneInfo('Australia/Perth'))
            else:
                # Fall back to createdAt if no effectiveDate
                creation_timestamp = invoice.get('createdAt', 0)
                if creation_timestamp:
                    date_obj = datetime.fromtimestamp(creation_timestamp, ZoneInfo('Australia/Perth'))
            
            if date_obj:
                # Daily data
                day_key = date_obj.strftime('%Y-%m-%d')
                daily_data[day_key]['transaction_count'] += 1
                daily_data[day_key]['revenue'] += amount
                daily_data[day_key]['service_count'] += len(operation_data.get('services', []))
                daily_data[day_key]['product_count'] += len(operation_data.get('orders', []))
                
                # Weekly data - get ISO week
                year, week, _ = date_obj.isocalendar()
                week_key = f"{year}-W{week:02d}"
                weekly_data[week_key]['transaction_count'] += 1
                weekly_data[week_key]['revenue'] += amount
                weekly_data[week_key]['service_count'] += len(operation_data.get('services', []))
                weekly_data[week_key]['product_count'] += len(operation_data.get('orders', []))
        
        # Calculate growth rates using weekly data
        sorted_weeks = sorted(weekly_data.keys())
        growth_rates = []
        
        for i in range(1, len(sorted_weeks)):
            prev_week = weekly_data[sorted_weeks[i-1]]
            curr_week = weekly_data[sorted_weeks[i]]
            
            if prev_week['revenue'] > 0:
                growth_rate = ((curr_week['revenue'] - prev_week['revenue']) / prev_week['revenue']) * 100
                growth_rates.append(growth_rate)
        
        avg_growth_rate = sum(growth_rates) / len(growth_rates) if growth_rates else 0
        
        # Calculate day-of-week patterns
        day_patterns = defaultdict(float)
        for day_key, day_data in daily_data.items():
            try:
                date_obj = datetime.strptime(day_key, '%Y-%m-%d').replace(tzinfo=ZoneInfo('Australia/Perth'))
                day_name = date_obj.strftime('%A')
                day_patterns[day_name] += day_data['revenue']
            except ValueError:
                continue
        
        return {
            'daily_transaction_counts': {k: v['transaction_count'] for k, v in daily_data.items()},
            'weekly_patterns': dict(day_patterns),
            'monthly_growth': {
                'growth_rate': round(avg_growth_rate, 2),
                'trend_direction': 'increasing' if avg_growth_rate > 0 else 'decreasing' if avg_growth_rate < 0 else 'stable'
            },
            'seasonal_insights': {
                'peak_day': max(day_patterns.items(), key=lambda x: x[1])[0] if day_patterns else 'N/A',
                'peak_revenue_day': max(daily_data.items(), key=lambda x: x[1]['revenue'])[0] if daily_data else 'N/A'
            },
            'weekly_trends': dict(weekly_data),
            'average_weekly_growth_rate': round(avg_growth_rate, 2),
            'trend_direction': 'increasing' if avg_growth_rate > 0 else 'decreasing' if avg_growth_rate < 0 else 'stable',
            'peak_week': max(weekly_data.items(), key=lambda x: x[1]['revenue']) if weekly_data else ('N/A', {}),
            'total_weeks_analyzed': len(weekly_data)
        }
    
    def _calculate_operational_metrics(self, invoices):
        """Calculate operational efficiency metrics"""
        total_services = 0
        total_products = 0
        mixed_transactions = 0  # Transactions with both services and products
        
        service_only_transactions = 0
        product_only_transactions = 0
        
        for invoice in invoices:
            operation_data = invoice.get('analyticsData', {}).get('operation_data', {})
            services = operation_data.get('services', [])
            orders = operation_data.get('orders', [])
            
            service_count = len(services)
            product_count = len(orders)
            
            total_services += service_count
            total_products += product_count
            
            if service_count > 0 and product_count > 0:
                mixed_transactions += 1
            elif service_count > 0:
                service_only_transactions += 1
            elif product_count > 0:
                product_only_transactions += 1
        
        total_transactions = len(invoices)
        
        return {
            'transaction_composition': {
                'service_only': service_only_transactions,
                'product_only': product_only_transactions,
                'mixed_service_product': mixed_transactions,
                'mixed_transaction_rate': round(
                    (mixed_transactions / total_transactions * 100), 2
                ) if total_transactions > 0 else 0
            },
            'average_items_per_transaction': {
                'services_per_transaction': round(total_services / total_transactions, 2) if total_transactions > 0 else 0,
                'products_per_transaction': round(total_products / total_transactions, 2) if total_transactions > 0 else 0
            },
            'cross_selling_metrics': {
                'cross_sell_success_rate': round(
                    (mixed_transactions / total_transactions * 100), 2
                ) if total_transactions > 0 else 0,
                'total_cross_sell_opportunities': total_transactions,
                'realized_cross_sells': mixed_transactions
            }
        }
    
    def _calculate_revenue_growth(self, daily_revenue, start_date_str, end_date_str):
        """Calculate revenue growth metrics"""
        if not daily_revenue:
            return {'growth_rate': 0, 'trend': 'no_data'}
        
        sorted_dates = sorted(daily_revenue.keys())
        if len(sorted_dates) < 2:
            return {'growth_rate': 0, 'trend': 'insufficient_data'}
        
        # Calculate overall growth from first to last period
        first_period_revenue = daily_revenue[sorted_dates[0]]
        last_period_revenue = daily_revenue[sorted_dates[-1]]
        
        if first_period_revenue > 0:
            overall_growth = ((last_period_revenue - first_period_revenue) / first_period_revenue) * 100
        else:
            overall_growth = 0
        
        # Determine trend
        if overall_growth > 5:
            trend = 'strong_growth'
        elif overall_growth > 0:
            trend = 'moderate_growth'
        elif overall_growth > -5:
            trend = 'stable'
        else:
            trend = 'declining'
        
        return {
            'overall_growth_rate': round(overall_growth, 2),
            'trend': trend,
            'first_period_revenue': first_period_revenue,
            'last_period_revenue': last_period_revenue,
            'periods_analyzed': len(sorted_dates)
        }
    
    def _calculate_age_distribution(self, vehicle_ages):
        """Calculate vehicle age distribution"""
        if not vehicle_ages:
            return {}
        
        age_ranges = {
            '0-2 years': 0,
            '3-5 years': 0,
            '6-10 years': 0,
            '11-15 years': 0,
            '16+ years': 0
        }
        
        for age in vehicle_ages:
            if age <= 2:
                age_ranges['0-2 years'] += 1
            elif age <= 5:
                age_ranges['3-5 years'] += 1
            elif age <= 10:
                age_ranges['6-10 years'] += 1
            elif age <= 15:
                age_ranges['11-15 years'] += 1
            else:
                age_ranges['16+ years'] += 1
        
        return age_ranges
    
    def _filter_analytics_by_type(self, analytics_result, analytics_type):
        """Filter analytics result by specific type"""
        type_mappings = {
            'revenue': ['summary', 'revenue_analytics'],
            'services': ['service_analytics'],
            'products': ['product_analytics'],
            'customers': ['customer_analytics'],
            'vehicles': ['vehicle_analytics'],
            'payments': ['payment_analytics'],
            'bookings': ['booking_analytics'],
            'trends': ['trend_analytics'],
            'operations': ['operational_metrics']
        }
        
        if analytics_type.lower() in type_mappings:
            filtered_keys = type_mappings[analytics_type.lower()]
            filtered_result = {
                'period': analytics_result['period'],
                'metadata': analytics_result['metadata']
            }
            
            for key in filtered_keys:
                if key in analytics_result:
                    filtered_result[key] = analytics_result[key]
            
            return filtered_result
        
        return analytics_result
    
    def get_quick_metrics(self, days_back=30):
        """
        Get quick dashboard metrics for the last N days
        
        Args:
            days_back: Number of days to look back (default 30)
            
        Returns:
            dict: Quick metrics for dashboard
        """
        end_date = datetime.now(ZoneInfo('Australia/Perth'))
        start_date = end_date - timedelta(days=days_back)
        
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        # Get comprehensive analytics but return only summary
        full_analytics = self.get_comprehensive_analytics(start_date_str, end_date_str)
        
        # Handle new service_analytics structure (service_table) for top_service
        service_analytics = full_analytics.get('service_analytics', {})
        top_service = ('N/A', 0)
        if 'service_table' in service_analytics and service_analytics['service_table']:
            # Use the service name and total revenue as top_service
            top = service_analytics['service_table'][0]
            top_service = (top['service'], round(top['preBookedRevenue'] + top['walkInRevenue'], 2))
        elif 'service_performance_ranking' in service_analytics and service_analytics['service_performance_ranking']:
            top_service = service_analytics['service_performance_ranking'][0]

        return {
            'period': full_analytics['period'],
            'quick_metrics': {
                'total_revenue': full_analytics['summary']['total_revenue'],
                'total_transactions': full_analytics['summary']['total_transactions'],
                'average_transaction_value': full_analytics['summary']['average_transaction_value'],
                'total_unique_customers': full_analytics['customer_analytics']['total_unique_customers'] if 'customer_analytics' in full_analytics and 'total_unique_customers' in full_analytics['customer_analytics'] else 0,
                'top_service': top_service,
                'top_product': full_analytics['product_analytics']['top_revenue_products'][0] if full_analytics['product_analytics']['top_revenue_products'] else ('N/A', 0),
                'most_common_vehicle_make': max(full_analytics['vehicle_analytics']['popular_makes'].items(), key=lambda x: x[1]) if full_analytics['vehicle_analytics']['popular_makes'] else ('N/A', 0),
                'preferred_payment_method': full_analytics['payment_analytics']['preferred_payment_method'][0],
                'pre_booking_rate': full_analytics['booking_analytics']['booking_statistics']['pre_booking_rate']
            },
            'metadata': full_analytics['metadata']
        }


def get_analytics_manager():
    """Factory function to get AnalyticsManager instance"""
    return AnalyticsManager()
